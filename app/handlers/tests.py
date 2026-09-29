"""Tests: create (AI or manual), schedule, post into the Test topic, grade."""

from __future__ import annotations

import re

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ..i18n import t
from ..models import TestQuestion
from ..services import notifier
from ..services import students as student_service
from ..services import tests as test_service
from ..services import topics as topic_service
from ..states import TestWizard
from ..utils import fmt_datetime, fmt_weekday, now, parse_time

router = Router(name="tests")
DRAFT = "test_draft"

WEEKDAYS = {
    "monday": 0, "mon": 0, "dushanba": 0,
    "tuesday": 1, "tue": 1, "seshanba": 1,
    "wednesday": 2, "wed": 2, "chorshanba": 2,
    "thursday": 3, "thu": 3, "payshanba": 3,
    "friday": 4, "fri": 4, "juma": 4,
    "saturday": 5, "sat": 5, "shanba": 5,
    "sunday": 6, "sun": 6, "yakshanba": 6,
}


def _parse_manual(text: str) -> dict | None:
    """Parse `Question?\na) one\n*b) two\nc) three\nd) four` into a question."""
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if len(lines) < 3:
        return None
    options: list[str] = []
    correct: int | None = None
    for line in lines[1:]:
        marked = line[0] in "*✓+"
        body = line.lstrip("*✓+ ").strip()
        match = re.match(r"^([a-dA-D])[\).\-\s]+(.+)$", body)
        if match:
            body = match.group(2).strip()
        if not body:
            continue
        if marked:
            correct = len(options)
        options.append(body)
    if len(options) < 2:
        return None
    return {
        "question": lines[0],
        "options": options[:4],
        "correct": correct if correct is not None else 0,
        "explanation": "",
    }


async def _deny(message: Message, lang: str, is_teacher: bool, is_class: bool) -> bool:
    if not is_teacher:
        await message.reply(t("only_teacher", lang))
        return True
    if not is_class:
        await message.reply(t("only_group", lang))
        return True
    return False


@router.message(Command("test", "testlar"))
async def cmd_test(
    message: Message,
    command: CommandObject,
    session,
    state: FSMContext,
    lang: str,
    is_teacher: bool,
    is_class: bool,
    chat_row,
) -> None:
    """`/test` menu plus the AI / manual / post / schedule sub-commands."""
    if await _deny(message, lang, is_teacher, is_class):
        return
    args = (command.args or "").strip().split()
    mode = args[0].lower() if args else ""

    # Using /test inside a topic teaches the bot where tests belong.
    await topic_service.detect_from_message(session, chat_row, "test", message)

    if not mode:
        text = t("test_menu", lang)
        if chat_row.is_forum and topic_service.thread_for(chat_row, "test") is None:
            text += "\n\n" + t("test_needs_topic", lang)
        await message.answer(text)
        return

    if mode in {"new", "ai", "generate"}:
        count = 10
        if len(args) > 1 and args[1].isdigit():
            count = max(3, min(25, int(args[1])))
        taught = await test_service.taught_topics(session, chat_row.id)
        if not taught:
            await message.reply(t("test_none_ready", lang))
            return
        await message.reply(
            t("test_new_started", lang, count=count,
              topics=notifier.esc(", ".join(taught[:4])))
        )
        test = await test_service.build_ai_test(
            session, chat_row, lang, count, created_by=message.from_user.id,
            thread_id=message.message_thread_id, title=f"Test — {taught[0]}",
        )
        if test is None:
            await message.reply(t("test_no_ai", lang))
            return
        total = len(await test_service.questions(session, test.id))
        await message.answer(
            t("test_created", lang, id=test.id, count=total,
              topics=notifier.esc(test.lesson_topics), minutes=test.duration_minutes)
        )
        return

    if mode in {"manual", "yozish"}:
        test = await test_service.create_test(
            session, chat_row.id, f"Test — {now().strftime('%d.%m.%Y')}",
            source="manual", created_by=message.from_user.id,
            duration_minutes=chat_row.test_duration or 30,
            thread_id=message.message_thread_id,
        )
        await state.set_state(TestWizard.manual)
        await state.update_data(**{DRAFT: test.id})
        await message.reply(t("test_manual_how", lang))
        return

    if mode in {"post", "send"}:
        candidates = await test_service.tests_for(session, chat_row.id)
        target = None
        if len(args) > 1 and args[1].lstrip("#").isdigit():
            target = await test_service.get_test(session, int(args[1].lstrip("#")))
        elif candidates:
            target = candidates[0]
        if target is None:
            await message.reply(t("test_none_ready", lang))
            return
        posted = await test_service.publish_test(
            bot=message.bot, session=session, test=target, chat=chat_row, lang=lang,
            thread_id=message.message_thread_id,
        )
        if not posted:
            await message.reply(t("test_none_ready", lang))
        return

    if mode in {"schedule", "rejalash"}:
        if len(args) < 3:
            await message.answer(t("test_menu", lang))
            return
        index = WEEKDAYS.get(args[1].lower())
        parsed = parse_time(args[2])
        if index is None or parsed is None:
            await message.answer(t("test_menu", lang))
            return
        chat_row.test_weekday = index
        chat_row.test_time = parsed.strftime("%H:%M")
        if len(args) > 3 and args[3].isdigit():
            chat_row.test_count = max(3, min(25, int(args[3])))
        await session.flush()
        await message.answer(
            t("test_scheduled", lang, weekday=fmt_weekday(index),
              time=chat_row.test_time, count=chat_row.test_count,
              minutes=chat_row.test_duration or 30)
        )
        return

    if mode in {"off", "stop"}:
        chat_row.test_weekday = None
        chat_row.test_time = None
        await session.flush()
        await message.answer(t("test_schedule_off", lang))
        return

    if mode in {"list", "royxat"}:
        items = await test_service.tests_for(session, chat_row.id)
        if not items:
            await message.reply(t("test_none_ready", lang))
            return
        lines = [t("test_list_title", lang), ""]
        for test in items:
            count = len(await test_service.questions(session, test.id))
            if test.status == "scheduled" and test.scheduled_at:
                status = t("test_status_scheduled", lang,
                           when=fmt_datetime(test.scheduled_at))
            else:
                status = t(f"test_status_{test.status}", lang)
            lines.append(t("test_list_line", lang, id=test.id,
                           title=notifier.esc(test.title), count=count, status=status))
        await message.answer("\n".join(lines))
        return

    await message.answer(t("test_menu", lang))


@router.message(TestWizard.manual, F.text)
async def manual_question(
    message: Message, session, state: FSMContext, lang: str
) -> None:
    if (message.text or "").startswith("/"):
        return  # /done and /cancel are handled by their own commands
    parsed = _parse_manual(message.text or "")
    if parsed is None:
        await message.reply(t("test_manual_bad", lang))
        return
    data = await state.get_data()
    test_id = int(data.get(DRAFT) or 0)
    if not test_id:
        await state.clear()
        await message.reply(t("test_menu", lang))
        return
    question = await test_service.add_question(
        session, test_id, parsed["question"], parsed["options"],
        parsed["correct"], parsed["explanation"],
    )
    total = len(await test_service.questions(session, test_id))
    await message.reply(t("test_added", lang, position=question.position, total=total))


@router.message(Command("done", "tugadi"))
async def cmd_done(message: Message, session, state: FSMContext) -> None:
    data = await state.get_data()
    test_id = int(data.get(DRAFT) or 0)
    await state.clear()
    if not test_id:
        return
    test = await test_service.get_test(session, test_id)
    if test is None:
        return
    total = len(await test_service.questions(session, test_id))
    lang = "bi"
    if not total:
        await message.reply(t("test_none_ready", lang))
        return
    await message.answer(
        t("test_created", lang, id=test.id, count=total,
          topics=notifier.esc(test.title), minutes=test.duration_minutes)
    )


@router.callback_query(F.data.startswith("test:"))
async def answer_question(callback: CallbackQuery, session, lang: str) -> None:
    """A student taps A/B/C/D — only they see the feedback.

    The late first tapper gets a free registration: answering with buttons is
    also how silent members become students.
    """
    parts = callback.data.split(":")
    if len(parts) != 4 or not parts[2].isdigit() or not parts[3].isdigit():
        await callback.answer()
        return
    test_id, question_id, choice = int(parts[1]), int(parts[2]), int(parts[3])
    question = await session.get(TestQuestion, question_id)
    if question is None or question.test_id != test_id:
        await callback.answer(t("test_answer_done", lang), show_alert=True)
        return
    test = await test_service.get_test(session, test_id)
    if test is not None:
        await student_service.touch_user(
            session, callback.from_user.id, test.chat_id,
            callback.from_user.full_name, callback.from_user.username,
        )
    _answer, is_new = await test_service.record_answer(
        session, test_id, question_id, callback.from_user.id, choice
    )
    if not is_new:
        await callback.answer(t("test_answer_done", lang), show_alert=True)
        return
    await test_service.score_question(session, question_id)
    options = list(question.options or [])
    correct_text = options[question.correct] if question.correct < len(options) else "—"
    if choice == question.correct:
        await callback.answer(
            t("test_answer_right", lang, explanation=question.explanation or ""),
            show_alert=True,
        )
    else:
        await callback.answer(
            t("test_answer_wrong", lang, answer=correct_text,
              explanation=question.explanation or ""),
            show_alert=True,
        )

