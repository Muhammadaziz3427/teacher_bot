"""Student submissions and their AI verdicts."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..ai_checker import CheckResult
from ..models import Homework, Submission
from ..utils import now


async def get(session: AsyncSession, homework_id: int, student_id: int) -> Submission | None:
    result = await session.execute(
        select(Submission).where(
            Submission.homework_id == homework_id, Submission.student_id == student_id
        )
    )
    return result.scalars().first()


async def get_by_id(session: AsyncSession, submission_id: int) -> Submission | None:
    return await session.get(Submission, submission_id)


async def upsert(
    session: AsyncSession,
    homework: Homework,
    student_id: int,
    content: str,
    media_file_id: str | None = None,
    media_type: str = "",
    message_id: int | None = None,
) -> Submission:
    """Create the submission, or update it when the student sends it again."""
    submission = await get(session, homework.id, student_id)
    is_late = now() > homework.due_at
    if submission is None:
        submission = Submission(
            homework_id=homework.id,
            student_id=student_id,
            chat_id=homework.chat_id,
            content=content or "",
            media_file_id=media_file_id,
            media_type=media_type or ("text" if content else "photo"),
            message_id=message_id,
            submitted_at=now(),
            is_late=is_late,
            attempts=1,
            status="pending",
        )
        session.add(submission)
    else:
        submission.content = content or submission.content
        submission.media_file_id = media_file_id or submission.media_file_id
        submission.media_type = media_type or submission.media_type
        submission.message_id = message_id or submission.message_id
        submission.submitted_at = now()
        submission.is_late = is_late
        submission.attempts = (submission.attempts or 1) + 1
        # a re-send is a new attempt: it must be checked again
        submission.status = "pending"
    await session.flush()
    return submission


async def apply_result(
    session: AsyncSession, submission: Submission, result: CheckResult
) -> Submission:
    submission.status = result.status
    submission.ai_score = result.score
    submission.ai_grade = result.grade
    submission.ai_verdict = result.verdict
    submission.ai_summary = result.summary
    submission.ai_mistakes = result.mistakes
    submission.ai_tasks = result.tasks
    submission.ai_topics = result.topics
    submission.ai_strengths = result.strengths
    submission.ai_tips = result.tips
    submission.ai_level = result.level
    submission.ai_raw = result.raw or {}
    await session.flush()
    return submission


async def set_manual(
    session: AsyncSession,
    submission: Submission,
    score: int,
    comment: str,
    graded_by: int,
) -> Submission:
    await apply_result(
        session,
        submission,
        CheckResult(
            ok=True,
            score=max(0, min(100, int(score))),
            summary=comment or submission.ai_summary,
            mistakes=submission.ai_mistakes or [],
            tasks=submission.ai_tasks or [],
            topics=submission.ai_topics or [],
        ),
    )
    submission.status = "manual"
    submission.teacher_comment = comment or ""
    submission.graded_by = graded_by
    await session.flush()
    return submission


async def set_points(session: AsyncSession, submission: Submission, points: float) -> None:
    submission.points_awarded = points
    await session.flush()


# --- Blok 4: the student confirms before the AI checks the work ----------
STATUS_AWAITING = "confirm"        # waiting for the student's ✅ button
STATUS_PENDING = "pending"         # queued / being checked by the worker


def is_awaiting(submission: Submission | None) -> bool:
    return submission is not None and submission.status == STATUS_AWAITING


async def mark_awaiting(session: AsyncSession, submission: Submission) -> Submission:
    """Park the work until the student confirms it (CONFIRM_SUBMISSIONS)."""
    submission.status = STATUS_AWAITING
    await session.flush()
    return submission


async def confirm(session: AsyncSession, submission: Submission) -> Submission:
    """The student pressed ✅ — the work is ready for the AI worker."""
    submission.status = STATUS_PENDING
    await session.flush()
    return submission


async def cancel(session: AsyncSession, submission: Submission) -> None:
    """The student pressed ❌ — nothing is counted, the row disappears."""
    await session.delete(submission)
    await session.flush()


async def awaiting_for(
    session, submission_id: int, student_id: int
) -> Submission | None:
    """Load a parked submission, but only for the student who owns it."""
    row = await get_by_id(session, submission_id)
    if row is None or row.student_id != student_id or not is_awaiting(row):
        return None
    return row


async def pending(session: AsyncSession, chat_id: int) -> list[Submission]:
    result = await session.execute(
        select(Submission)
        .where(Submission.chat_id == chat_id, Submission.status == "pending")
        .order_by(Submission.submitted_at)
    )
    return list(result.scalars().all())


async def awaiting(session: AsyncSession, homework_id: int) -> list[Submission]:
    """Parked submissions of one homework (CONFIRM_SUBMISSIONS is on)."""
    result = await session.execute(
        select(Submission)
        .where(Submission.homework_id == homework_id,
               Submission.status == STATUS_AWAITING)
        .order_by(Submission.submitted_at)
    )
    return list(result.scalars().all())


async def for_homework(session: AsyncSession, homework_id: int) -> list[Submission]:
    result = await session.execute(
        select(Submission)
        .where(Submission.homework_id == homework_id)
        .order_by(Submission.submitted_at)
    )
    return list(result.scalars().all())


async def submitted_ids(session: AsyncSession, homework_id: int) -> set[int]:
    result = await session.execute(
        select(Submission.student_id).where(Submission.homework_id == homework_id)
    )
    return {int(row[0]) for row in result.all()}


async def for_student(
    session: AsyncSession,
    chat_id: int,
    student_id: int,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> list[Submission]:
    stmt = select(Submission).where(
        Submission.chat_id == chat_id, Submission.student_id == student_id
    )
    if start is not None:
        stmt = stmt.where(Submission.submitted_at >= start)
    if end is not None:
        stmt = stmt.where(Submission.submitted_at <= end)
    result = await session.execute(stmt.order_by(Submission.submitted_at))
    return list(result.scalars().all())


async def between(
    session: AsyncSession, chat_id: int, start: datetime, end: datetime
) -> list[Submission]:
    result = await session.execute(
        select(Submission).where(
            Submission.chat_id == chat_id,
            Submission.submitted_at >= start,
            Submission.submitted_at <= end,
        )
    )
    return list(result.scalars().all())


async def count_between(
    session: AsyncSession, chat_id: int, start: datetime, end: datetime
) -> int:
    result = await session.execute(
        select(func.count()).select_from(Submission).where(
            Submission.chat_id == chat_id,
            Submission.submitted_at >= start,
            Submission.submitted_at <= end,
        )
    )
    return int(result.scalar() or 0)


async def stats(
    session: AsyncSession,
    chat_id: int,
    student_id: int,
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    """Submission-level numbers for one student inside a period."""
    rows = await for_student(session, chat_id, student_id, start, end)
    graded = [r for r in rows if r.status in {"checked", "manual"}]
    scores = [r.ai_score for r in graded]
    return {
        "submitted": len(rows),
        "done": len(rows),
        "late": sum(1 for r in rows if r.is_late),
        "ontime": sum(1 for r in rows if not r.is_late),
        "avg": round(sum(scores) / len(scores), 1) if scores else 0.0,
        "best": max(scores) if scores else 0,
        "lowest": min(scores) if scores else 0,
    }


def mistake_categories(rows: list[Submission]) -> dict[str, int]:
    """Aggregate mistake categories across submissions (most frequent first)."""
    counter: dict[str, int] = {}
    for row in rows:
        for mistake in row.ai_mistakes or []:
            if not isinstance(mistake, dict):
                continue
            key = str(mistake.get("category") or "other").strip().lower() or "other"
            counter[key] = counter.get(key, 0) + 1
    return dict(sorted(counter.items(), key=lambda item: item[1], reverse=True))


def mistake_rules(rows: list[Submission]) -> list[str]:
    """Most useful recurring rules (used for 'next focus' advice)."""
    counter: dict[str, int] = {}
    for row in rows:
        for mistake in row.ai_mistakes or []:
            if not isinstance(mistake, dict):
                continue
            rule = str(mistake.get("rule") or "").strip()
            if rule:
                counter[rule] = counter.get(rule, 0) + 1
    ordered = sorted(counter.items(), key=lambda item: item[1], reverse=True)
    return [rule for rule, _ in ordered[:3]]


def strengths(rows: list[Submission]) -> list[str]:
    seen: list[str] = []
    for row in rows:
        for item in row.ai_strengths or []:
            text = str(item).strip()
            if text and text not in seen:
                seen.append(text)
    return seen[:4]

