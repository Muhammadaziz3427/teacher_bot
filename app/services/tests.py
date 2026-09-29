"""Quizzes: create, schedule, post into the Test topic, collect answers."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Chat, Homework, Test, TestAnswer, TestQuestion, User
from ..utils import now


async def create_test(
    session: AsyncSession,
    chat_id: int,
    title: str,
    lesson_topics: str = "",
    source: str = "manual",
    created_by: int = 0,
    duration_minutes: int = 30,
    thread_id: int | None = None,
) -> Test:
    test = Test(
        chat_id=chat_id,
        title=title[:255],
        lesson_topics=lesson_topics[:500],
        source=source,
        created_by=created_by,
        duration_minutes=max(5, min(duration_minutes, 600)),
        thread_id=thread_id,
        status="draft",
    )
    session.add(test)
    await session.flush()
    return test


async def add_question(
    session: AsyncSession,
    test_id: int,
    text: str,
    options: Sequence[str],
    correct: int,
    explanation: str = "",
) -> TestQuestion:
    question = TestQuestion(
        test_id=test_id,
        position=await next_position(session, test_id),
        text=text.strip(),
        options=[str(o).strip() for o in options][:4],
        correct=max(0, min(3, int(correct))),
        explanation=explanation.strip()[:500],
    )
    session.add(question)
    await session.flush()
    return question


async def next_position(session: AsyncSession, test_id: int) -> int:
    result = await session.execute(
        select(func.coalesce(func.max(TestQuestion.position), 0)).where(
            TestQuestion.test_id == test_id
        )
    )
    return int(result.scalar() or 0) + 1


async def questions(session: AsyncSession, test_id: int) -> list[TestQuestion]:
    result = await session.execute(
        select(TestQuestion)
        .where(TestQuestion.test_id == test_id)
        .order_by(TestQuestion.position)
    )
    return list(result.scalars().all())


async def get_test(session: AsyncSession, test_id: int) -> Test | None:
    return await session.get(Test, test_id)


async def tests_for(session: AsyncSession, chat_id: int, limit: int = 10) -> list[Test]:
    result = await session.execute(
        select(Test)
        .where(Test.chat_id == chat_id, Test.status.in_(("draft", "scheduled", "running")))
        .order_by(Test.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def schedule_test(
    session: AsyncSession, test: Test, moment: datetime, thread_id: int | None = None
) -> Test:
    test.scheduled_at = moment
    test.status = "scheduled"
    if thread_id is not None:
        test.thread_id = thread_id
    await session.flush()
    return test


async def due_tests(session: AsyncSession, moment: datetime) -> list[Test]:
    """Scheduled tests whose time has come (not posted yet)."""
    result = await session.execute(
        select(Test)
        .where(Test.status == "scheduled", Test.scheduled_at <= moment)
        .order_by(Test.scheduled_at)
    )
    return list(result.scalars().all())


async def ending_tests(session: AsyncSession, moment: datetime) -> list[Test]:
    """Running tests whose answering window has closed."""
    result = await session.execute(
        select(Test).where(
            Test.status == "running", Test.ends_at.isnot(None), Test.ends_at <= moment
        )
    )
    return list(result.scalars().all())


async def mark_running(session: AsyncSession, test: Test, thread_id: int | None) -> Test:
    test.status = "running"
    test.posted_at = now()
    test.ends_at = now() + timedelta(minutes=test.duration_minutes)
    if thread_id is not None:
        test.thread_id = thread_id
    await session.flush()
    return test


async def mark_finished(session: AsyncSession, test: Test) -> Test:
    test.status = "finished"
    await session.flush()
    return test


async def record_answer(
    session: AsyncSession, test_id: int, question_id: int, student_id: int, choice: int
) -> tuple[TestAnswer, bool]:
    """Upsert the answer; returns (answer, is_new)."""
    result = await session.execute(
        select(TestAnswer).where(
            TestAnswer.question_id == question_id, TestAnswer.student_id == student_id
        )
    )
    answer = result.scalars().first()
    new = answer is None
    if answer is None:
        answer = TestAnswer(
            test_id=test_id, question_id=question_id, student_id=student_id,
            choice=choice, is_correct=False,
        )
        session.add(answer)
    answer.choice = choice
    await session.flush()
    return answer, new


async def score_question(session: AsyncSession, question_id: int) -> None:
    """Recompute correctness for every answer to one question."""
    question = await session.get(TestQuestion, question_id)
    if question is None:
        return
    result = await session.execute(
        select(TestAnswer).where(TestAnswer.question_id == question_id)
    )
    for answer in result.scalars().all():
        answer.is_correct = answer.choice == question.correct
    await session.flush()


async def leaderboard(session: AsyncSession, test_id: int) -> list[tuple[int, int]]:
    """[(student_tg_id, correct_count)] sorted by score.

    Everyone who answered appears — a student who got everything wrong is
    listed with 0, otherwise they would look like they never took the test.
    """
    items = await questions(session, test_id)
    correct_map = {q.id: q.correct for q in items}
    result = await session.execute(select(TestAnswer).where(TestAnswer.test_id == test_id))
    scores: dict[int, int] = {}
    for answer in result.scalars().all():
        scores.setdefault(int(answer.student_id), 0)
        if answer.question_id in correct_map and answer.choice == correct_map[answer.question_id]:
            scores[int(answer.student_id)] += 1
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)


async def answered_students(session: AsyncSession, test_id: int) -> list[int]:
    result = await session.execute(
        select(TestAnswer.student_id)
        .where(TestAnswer.test_id == test_id)
        .group_by(TestAnswer.student_id)
    )
    return [int(row[0]) for row in result.all()]


async def taught_topics(session: AsyncSession, chat_id: int, limit: int = 8) -> list[str]:
    """Lesson titles the class was actually given — the test syllabus."""
    result = await session.execute(
        select(Homework.title)
        .where(Homework.chat_id == chat_id, Homework.title != "")
        .order_by(Homework.due_at.desc())
        .limit(limit)
    )
    return [row[0] for row in result.all()]


# --------------------------------------------------------------------------
# Orchestration — shared by the /test handlers and the background scheduler
# --------------------------------------------------------------------------
async def publish_test(
    bot,
    session: AsyncSession,
    test: Test,
    chat: Chat | None,
    lang: str,
    thread_id: int | None = None,
) -> int:
    """Post every question into the Test topic and start the answering clock."""
    from . import notifier, topics as topic_service

    items = await questions(session, test.id)
    if not items:
        return 0
    thread = thread_id if thread_id is not None else (
        test.thread_id or topic_service.thread_for(chat, "test")
    )
    await mark_running(session, test, thread)
    await notifier.send_long(
        bot,
        test.chat_id,
        t_("test_posted", lang, id=test.id, title=_esc(test.title),
           count=len(items), minutes=test.duration_minutes),
        thread_id=thread,
    )
    for index, question in enumerate(items, start=1):
        question.message_id = await notifier.send_question(
            bot, test.chat_id, question, index, len(items), test.id, lang, thread
        )
    await session.flush()
    return len(items)


async def finish_test(
    bot, session: AsyncSession, test: Test, chat: Chat | None, lang: str
) -> str:
    """Post the class results, DM each student their score, finish the test."""
    from . import notifier, topics as topic_service
    from . import students as student_service

    students = await student_service.list_students(session, test.chat_id)
    scores = dict(await leaderboard(session, test.id))
    total = len(await questions(session, test.id))
    thread = test.thread_id or topic_service.thread_for(chat, "test")

    lines = [t_("test_results", lang, id=test.id, title=_esc(test.title),
                answered=len(scores), students=len(students))]
    if scores:
        by_id = {student.tg_id: student for student in students}
        for place, (student_id, score) in enumerate(scores.items(), start=1):
            student = by_id.get(student_id)
            name = _esc(student.full_name) if student else str(student_id)
            lines.append(t_("test_result_line", lang, place=place, name=name,
                            score=score, total=total))
        missing = [s.full_name for s in students if s.tg_id not in scores]
        if missing:
            lines.append("")
            lines.append("🚫 " + ", ".join(_esc(name) for name in missing[:20]))
    else:
        lines.append(t_("test_no_answers", lang))

    await notifier.send_long(bot, test.chat_id, "\n".join(lines), thread_id=thread)
    for student in students:
        if student.tg_id in scores:
            try:
                await bot.send_message(
                    student.tg_id,
                    t_("test_personal_result", lang, id=test.id,
                      score=scores[student.tg_id], total=total),
                )
            except Exception:
                continue
    await mark_finished(session, test)
    return "\n".join(lines)


async def build_ai_test(
    session: AsyncSession,
    chat: Chat,
    lang: str,
    count: int,
    topics: Sequence[str] | None = None,
    created_by: int = 0,
    thread_id: int | None = None,
    title: str = "",
) -> Test | None:
    """Create a ready-to-post test with AI questions from the lessons taught."""
    from ..ai_checker import generate_test

    chosen = list(topics) if topics else await taught_topics(session, chat.id)
    if not chosen:
        return None
    questions_data = await generate_test(chosen, count=count, lang=lang,
                                         level=chat.level or "",
                                         taught=chosen)
    if not questions_data:
        return None
    test = await create_test(
        session, chat.id,
        title=title or f"Test — {', '.join(chosen[:2])}",
        lesson_topics=", ".join(chosen[:6]),
        source="ai", created_by=created_by,
        duration_minutes=chat.test_duration or 30,
        thread_id=thread_id,
    )
    for item in questions_data:
        await add_question(session, test.id, item["question"], item["options"],
                           item["correct"], item.get("explanation", ""))
    return test


def t_(key: str, lang: str, **kwargs) -> str:
    from ..i18n import t

    return t(key, lang, **kwargs)


def _esc(value: object) -> str:
    from .notifier import esc

    return esc(value)
