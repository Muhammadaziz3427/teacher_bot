"""Teacher commands: homework wizard, attendance, grading, penalties, timetable."""

from __future__ import annotations

from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from ..config import settings
from ..i18n import attendance_status_label, grade_for, skill_label, t
from ..keyboards import (
    attendance_kb,
    back_sections_kb,
    cancel_kb,
    confirm_kb,
    dash_periods_kb,
    due_kb,
    groups_kb,
    homework_actions_kb,
    homework_list_kb,
    media_kb,
    pending_kb,
    sections_kb,
    skills_kb,
)
from ..models import Chat
from ..services import attendance as attendance_service
from ..services import exporter
from ..services import homework as homework_service
from ..services import notifier
from ..services import schedule as schedule_service
from ..services import scoring
from ..services import students as student_service
from ..services import submissions as submission_service
from ..services import reports as reports_service
from ..services import topics as topic_service
from ..states import HomeworkWizard, ManualGrade
from ..utils import fmt_date_short, fmt_datetime, fmt_weekday, parse_due, parse_time, today

router = Router(name="teacher")
DRAFT = "hw_draft"


def _deny(message: Message, lang: str, is_teacher: bool, is_class: bool = True) -> bool:
    """Return True when the caller is not allowed to run the command."""
    if not is_teacher:
        return True
    if not is_class:
        return True
    return False


async def _say_deny(message: Message, lang: str, is_teacher: bool, is_class: bool = True) -> bool:
    """Deny with a visible message (used by group commands)."""
    denied = _deny(message, lang, is_teacher, is_class)
    if denied:
        await message.reply(
            t("only_teacher", lang) if not is_teacher else t("only_group", lang)
        )
    return denied


def _esc(value: object) -> str:
    return notifier.esc(value)


def _draft_preview(draft: dict, lang: str) -> str:
    lines = [t("hw_preview", lang), ""]
    lines.append(f"📚 <b>{notifier.esc(draft.get('title') or '—')}</b>")
    if draft.get("skill"):
        lines.append(f"🎯 {notifier.esc(skill_label(draft['skill'], lang))}")
    if draft.get("description"):
        lines.append(notifier.esc(draft["description"]))
    if draft.get("due_at"):
        lines.append(f"⏰ {fmt_datetime(datetime.fromisoformat(draft['due_at']))}")
    if draft.get("media_file_id"):
        lines.append("🖼 + photo/document")
    return "\n".join(lines)


@router.message(Command("homework", "vazifa", "hw"))
async def cmd_homework(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    session,
    lang: str,
    is_teacher: bool,
    is_class: bool,
    chat_row,
) -> None:
    if await _say_deny(message, lang, is_teacher, is_class):
        return
    # Using /homework inside a topic teaches the bot where homework belongs.
    await topic_service.detect_from_message(session, chat_row, "homework", message)
    draft: dict = {}
    replied = message.reply_to_message
    if replied is not None:
        text = replied.text or replied.caption or ""
        if text:
            draft["description"] = text
        if replied.photo:
            draft["media_file_id"] = replied.photo[-1].file_id
            draft["media_type"] = "photo"
        elif replied.document:
            draft["media_file_id"] = replied.document.file_id
            draft["media_type"] = "document"
        if getattr(replied, "message_thread_id", None):
            draft["thread_id"] = replied.message_thread_id
    if message.message_thread_id:
        draft["thread_id"] = message.message_thread_id

    args = (command.args or "").strip()
    if args:
        draft["title"] = args

    await state.update_data(**{DRAFT: draft})
    if draft.get("title"):
        await state.set_state(HomeworkWizard.skill)
        await message.reply(t("hw_ask_skill", lang), reply_markup=skills_kb(lang))
        return
    await state.set_state(HomeworkWizard.title)
    await message.reply(t("hw_ask_title", lang), reply_markup=cancel_kb(lang))


@router.message(HomeworkWizard.title)
async def wizard_title(message: Message, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    draft = data.get(DRAFT) or {}
    draft["title"] = (message.text or "").strip()[:255]
    await state.update_data(**{DRAFT: draft})
    await state.set_state(HomeworkWizard.skill)
    await message.answer(t("hw_ask_skill", lang), reply_markup=skills_kb(lang))


@router.callback_query(F.data.startswith("wiz:skill:"))
async def wizard_skill(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    draft = data.get(DRAFT) or {}
    if not draft.get("title"):
        await state.clear()
        await callback.answer(t("cancelled", lang), show_alert=True)
        return
    draft["skill"] = callback.data.split(":")[2]
    await state.update_data(**{DRAFT: draft})
    await state.set_state(HomeworkWizard.description)
    await callback.message.answer(t("hw_ask_desc", lang), reply_markup=cancel_kb(lang))
    await callback.answer()


@router.message(HomeworkWizard.description)
async def wizard_description(message: Message, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    draft = data.get(DRAFT) or {}
    draft["description"] = (message.text or "").strip()
    await state.update_data(**{DRAFT: draft})
    await state.set_state(HomeworkWizard.due)
    await message.answer(t("hw_ask_deadline", lang), reply_markup=due_kb(lang))


@router.message(HomeworkWizard.due)
async def wizard_due(message: Message, state: FSMContext, lang: str, session) -> None:
    raw = (message.text or "").strip()
    if raw in {"-", "next", "auto", "keyingi", ""}:
        due = await schedule_service.default_due(session, message.chat.id)
    else:
        due = parse_due(raw)
        if due is None:
            await message.answer(t("hw_deadline_bad", lang))
            return
    draft = (await state.get_data()).get(DRAFT) or {}
    draft["due_at"] = due.isoformat()
    await state.update_data(**{DRAFT: draft})
    await state.set_state(HomeworkWizard.media)
    await message.answer(t("hw_ask_media", lang), reply_markup=media_kb(lang))


@router.callback_query(F.data == "wiz:due_default")
async def wizard_due_default(
    callback: CallbackQuery, state: FSMContext, lang: str, session
) -> None:
    due = await schedule_service.default_due(session, callback.message.chat.id)
    draft = (await state.get_data()).get(DRAFT) or {}
    draft["due_at"] = due.isoformat()
    await state.update_data(**{DRAFT: draft})
    await state.set_state(HomeworkWizard.media)
    await callback.message.answer(t("hw_ask_media", lang), reply_markup=media_kb(lang))
    await callback.answer()


async def _show_confirm(state: FSMContext, session, chat_id: int, lang: str, send) -> None:
    """Move to the confirm step, filling in a default deadline when needed."""
    draft = (await state.get_data()).get(DRAFT) or {}
    if not draft.get("due_at"):
        due = await schedule_service.default_due(session, chat_id)
        draft["due_at"] = due.isoformat()
        await state.update_data(**{DRAFT: draft})
    await state.set_state(HomeworkWizard.confirm)
    await send(_draft_preview(draft, lang), reply_markup=confirm_kb(lang))


@router.message(HomeworkWizard.media, F.photo)
async def wizard_media_photo(
    message: Message, state: FSMContext, lang: str, session
) -> None:
    draft = (await state.get_data()).get(DRAFT) or {}
    draft["media_file_id"] = message.photo[-1].file_id
    draft["media_type"] = "photo"
    await state.update_data(**{DRAFT: draft})
    await _show_confirm(state, session, message.chat.id, lang, message.answer)


@router.message(HomeworkWizard.media, F.document)
async def wizard_media_document(
    message: Message, state: FSMContext, lang: str, session
) -> None:
    draft = (await state.get_data()).get(DRAFT) or {}
    draft["media_file_id"] = message.document.file_id
    draft["media_type"] = "document"
    await state.update_data(**{DRAFT: draft})
    await _show_confirm(state, session, message.chat.id, lang, message.answer)


@router.message(HomeworkWizard.media, F.text)
async def wizard_media_text(message: Message, state: FSMContext, lang: str, session) -> None:
    draft = (await state.get_data()).get(DRAFT) or {}
    extra = (message.text or "").strip()
    if extra:
        draft["description"] = (draft.get("description", "") + "\n" + extra).strip()
    await state.update_data(**{DRAFT: draft})
    await _show_confirm(state, session, message.chat.id, lang, message.answer)


@router.callback_query(F.data == "wiz:skip")
async def wizard_skip(callback: CallbackQuery, state: FSMContext, lang: str, session) -> None:
    await callback.answer()
    await _show_confirm(state, session, callback.message.chat.id, lang, callback.message.answer)


@router.callback_query(F.data == "wiz:cancel")
async def wizard_cancel(callback: CallbackQuery, state: FSMContext, lang: str) -> None:
    await state.clear()
    await callback.message.answer(t("cancelled", lang))
    await callback.answer()


@router.callback_query(F.data == "wiz:confirm")
async def wizard_confirm(
    callback: CallbackQuery,
    state: FSMContext,
    session,
    lang: str,
    bot: Bot,
    is_teacher: bool,
) -> None:
    if not is_teacher:
        await callback.answer(t("only_teacher", lang), show_alert=True)
        return
    draft = (await state.get_data()).get(DRAFT) or {}
    chat_id = callback.message.chat.id
    chat_row = await student_service.get_chat(session, chat_id)
    due = (
        datetime.fromisoformat(draft["due_at"])
        if draft.get("due_at")
        else await schedule_service.default_due(session, chat_id)
    )
    thread = draft.get("thread_id") or topic_service.thread_for(chat_row, "homework")
    homework = await homework_service.create(
        session,
        chat_id,
        title=draft.get("title") or "Homework",
        description=draft.get("description", ""),
        due_at=due,
        created_by=callback.from_user.id,
        skill=draft.get("skill", ""),
        criteria=draft.get("criteria", ""),
        media_file_id=draft.get("media_file_id"),
        media_type=draft.get("media_type", ""),
        thread_id=thread,
    )
    await state.clear()
    message_id = await notifier.publish_homework(bot, homework, lang, thread_id=thread)
    if message_id:
        await homework_service.attach_message(session, homework, message_id)
    await callback.message.answer(
        t("hw_created", lang, id=homework.id, due=fmt_datetime(due), rel="→")
    )
    await callback.answer()


@router.message(Command("homeworks", "vazifalar"))
async def cmd_homeworks(message: Message, session, lang: str, is_teacher: bool, is_class: bool) -> None:
    if await _say_deny(message, lang, is_teacher, is_class):
        return
    items = await homework_service.active(session, message.chat.id)
    if not items:
        await message.reply(t("hw_none", lang))
        return
    lines = [t("hw_list", lang), ""]
    for homework in items:
        overview = await homework_service.overview(session, homework)
        lines.append(
            f"#{homework.id} <b>{notifier.esc(homework.title)}</b>\n"
            f"   ⏰ {fmt_datetime(homework.due_at)} · ✅ {overview['submitted']} · "
            f"⏰ {overview['late']} · ⏳ {overview['pending']}"
        )
    await message.answer("\n".join(lines), reply_markup=homework_list_kb(items, lang))


@router.callback_query(F.data.startswith("hw:view:"))
async def hw_view(callback: CallbackQuery, session, lang: str) -> None:
    homework = await homework_service.get(session, int(callback.data.split(":")[2]))
    if homework is None:
        await callback.answer(t("hw_none", lang), show_alert=True)
        return
    rows = await submission_service.for_homework(session, homework.id)
    students = await student_service.list_students(session, homework.chat_id)
    submitted = {row.student_id for row in rows}
    scores = [row.ai_score for row in rows if row.status in {"checked", "manual"}]
    lines = [
        notifier.render_homework(homework, lang),
        "",
        f"✅ {len(submitted)}/{len(students)}",
        f"📊 avg {round(sum(scores) / len(scores), 1) if scores else 0}",
    ]
    missing = [s.full_name for s in students if s.tg_id not in submitted]
    if missing:
        lines.append("🚫 " + ", ".join(notifier.esc(name) for name in missing[:20]))
    await callback.message.answer("\n".join(lines),
                                 reply_markup=homework_actions_kb(homework.id, lang))
    await callback.answer()


@router.callback_query(F.data.startswith("hw:close:"))
async def hw_close(
    callback: CallbackQuery, session, lang: str, bot: Bot, is_teacher: bool
) -> None:
    if not is_teacher:
        await callback.answer(t("only_teacher", lang), show_alert=True)
        return
    homework = await homework_service.get(session, int(callback.data.split(":")[2]))
    if homework is None:
        await callback.answer(t("hw_none", lang), show_alert=True)
        return
    from ..scheduler import close_homework_and_penalise

    await close_homework_and_penalise(bot, session, homework, lang)
    await callback.message.answer(t("hw_closed", lang, id=homework.id))
    await callback.answer()


@router.callback_query(F.data.startswith("hw:remind:"))
async def hw_remind(callback: CallbackQuery, session, lang: str, bot: Bot) -> None:
    homework = await homework_service.get(session, int(callback.data.split(":")[2]))
    if homework is None:
        await callback.answer(t("hw_none", lang), show_alert=True)
        return
    await notifier.send_reminder(bot, homework, 0, lang)
    await callback.answer(t("hw_reminded", lang), show_alert=False)


@router.callback_query(F.data.startswith("hw:stats:"))
async def hw_stats(callback: CallbackQuery, session, lang: str) -> None:
    homework = await homework_service.get(session, int(callback.data.split(":")[2]))
    if homework is None:
        await callback.answer(t("hw_none", lang), show_alert=True)
        return
    rows = await submission_service.for_homework(session, homework.id)
    students = await student_service.list_students(session, homework.chat_id)
    by_id = {student.tg_id: student for student in students}
    lines = [t("hw_list", lang) + f" #{homework.id}", ""]
    for row in rows:
        student = by_id.get(row.student_id)
        name = notifier.esc(student.full_name) if student else str(row.student_id)
        flag = "⏰" if row.is_late else "✅"
        lines.append(f"{flag} {name} — {row.ai_score}/100 ({row.ai_grade or '-'}) · "
                     f"{row.points_awarded} pts")
    missing = [s for s in students if s.tg_id not in {r.student_id for r in rows}]
    if missing:
        lines.append("")
        lines.append("🚫 " + ", ".join(notifier.esc(s.full_name) for s in missing))
    await callback.message.answer("\n".join(lines))
    await callback.answer()


@router.message(Command("groups", "guruhlar"))
async def cmd_groups(
    message: Message, session, lang: str, is_teacher: bool, is_class: bool
) -> None:
    """List the groups where the caller is registered as staff."""
    if is_class:
        await message.reply(t("dash_open", lang))
        return
    if not is_teacher:
        await message.reply(t("only_teacher", lang))
        return
    chats = await student_service.teacher_chats(session, message.from_user.id)


async def _dashboard_groups_text(session, chats, lang: str) -> str:
    lines = [t("menu_dashboard", lang), "", t("dash_pick_group", lang), ""]
    for chat in chats:
        students = await student_service.count_students(session, chat.id)
        active = await homework_service.count_active(session, chat.id)
        lines.append(
            f"🏫 <b>{_esc(chat.title or str(chat.id))}</b>\n"
            f"   {t('dash_group_line', lang, students=students, active=active)}"
        )
    return "\n".join(lines)


async def _section_overview_text(session, chat: Chat, lang: str) -> str:
    students = await student_service.list_students(session, chat.id)
    active = await homework_service.active(session, chat.id)
    day = today()
    marks = await attendance_service.for_day(session, chat.id, day)
    present = sum(1 for row in marks.values() if row.status == "present")
    late = sum(1 for row in marks.values() if row.status == "late")
    absent = sum(1 for row in marks.values() if row.status == "absent")
    if active:
        first = active[0]
        next_task = f"#{first.id} {_esc(first.title)} — ⏰ {fmt_datetime(first.due_at)}"
    else:
        next_task = t("dash_next_none", lang)
    if students and active:
        scores = await reports_service.collect_all(session, chat.id, "weekly")
        leader = max(scores, key=lambda s: (s.points, s.avg)).student.full_name
    else:
        leader = t("dash_leader_none", lang)
    return t(
        "dash_overview", lang, title=_esc(chat.title or str(chat.id)),
        students=len(students), active=len(active), today=fmt_date_short(day),
        present=present, late=late, absent=absent, next_task=next_task, leader=_esc(leader),
    )


async def _deny_dash(callback: CallbackQuery, session, lang: str, chat_id: int) -> "Chat | None":
    """Dashboard access check; toasts and returns None when denied."""
    chat = await session.get(Chat, chat_id)
    if chat is None or not await student_service.can_open_group(
        session, callback.from_user.id, chat_id
    ):
        await callback.answer(t("only_manager", lang), show_alert=True)
        return None
    return chat


@router.callback_query(F.data == "dash:groups:0")
async def dash_groups(callback: CallbackQuery, session, lang: str) -> None:
    chats = await student_service.teacher_chats(session, callback.from_user.id)
    if not chats:
        await callback.answer(t("dash_no_groups", lang), show_alert=True)
        return
    text = await _dashboard_groups_text(session, chats, lang)
    try:
        await callback.message.edit_text(text, reply_markup=groups_kb(chats, lang))
    except Exception:
        await callback.message.answer(text, reply_markup=groups_kb(chats, lang))
    await callback.answer()


@router.callback_query(F.data.startswith("dash:open:"))
async def dash_open(callback: CallbackQuery, session, lang: str) -> None:
    chat = await _deny_dash(callback, session, lang, int(callback.data.split(":")[2]))
    if chat is None:
        return
    await callback.message.answer(
        t("dash_sections", lang, title=_esc(chat.title or str(chat.id))),
        reply_markup=sections_kb(chat.id, lang),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("dash:overview:"))
async def dash_overview(callback: CallbackQuery, session, lang: str) -> None:
    chat = await _deny_dash(callback, session, lang, int(callback.data.split(":")[2]))
    if chat is None:
        return
    await callback.message.answer(
        await _section_overview_text(session, chat, lang),
        reply_markup=back_sections_kb(chat.id, lang),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("dash:attendance:"))
async def dash_attendance(callback: CallbackQuery, session, lang: str) -> None:
    chat = await _deny_dash(callback, session, lang, int(callback.data.split(":")[2]))
    if chat is None:
        return
    day = today()
    rows = await attendance_service.for_day(session, chat.id, day)
    marks = {sid: row.status for sid, row in rows.items()}
    students = await student_service.list_students(session, chat.id)
    if not students:
        await callback.answer(t("att_none", lang), show_alert=True)
        return
    await callback.message.answer(
        f"{t('att_title', lang, date=fmt_date_short(day))}\n"
        f"{t('att_help', lang)}\n{t('dash_att_hint', lang)}",
        reply_markup=attendance_kb(students, marks, lang, chat.id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("dash:homeworks:"))
async def dash_homeworks(callback: CallbackQuery, session, lang: str) -> None:
    chat = await _deny_dash(callback, session, lang, int(callback.data.split(":")[2]))
    if chat is None:
        return
    items = await homework_service.active(session, chat.id)
    lines = [t("dash_homework_hint", lang), ""]
    for homework in items[:15]:
        overview = await homework_service.overview(session, homework)
        lines.append(
            f"#{homework.id} <b>{_esc(homework.title)}</b>\n"
            f"   ⏰ {fmt_datetime(homework.due_at)} · ✅ {overview['submitted']} · "
            f"⏳ {overview['pending']}"
        )
    if not items:
        lines.append(t("hw_none", lang))
    await callback.message.answer("\n".join(lines),
                                  reply_markup=back_sections_kb(chat.id, lang))
    await callback.answer()


@router.callback_query(F.data.startswith("dash:students:"))
async def dash_students(callback: CallbackQuery, session, lang: str) -> None:
    chat = await _deny_dash(callback, session, lang, int(callback.data.split(":")[2]))
    if chat is None:
        return
    ranking = await reports_service.ranking(session, chat.id, "weekly", lang)
    await callback.message.answer(
        f"{t('dash_students_hint', lang)}\n\n{ranking}",
        reply_markup=back_sections_kb(chat.id, lang),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("dash:reports:"))
async def dash_reports(callback: CallbackQuery, session, lang: str) -> None:
    chat = await _deny_dash(callback, session, lang, int(callback.data.split(":")[2]))
    if chat is None:
        return
    await callback.message.answer(
        f"{t('dash_reports_hint', lang)}\n\n{t('dash_export_hint', lang)}",
        reply_markup=dash_periods_kb(chat.id, lang),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("dash:repw:"))
async def dash_report_weekly(callback: CallbackQuery, session, lang: str) -> None:
    await _dash_send_group_report(callback, session, lang, "weekly")


@router.callback_query(F.data.startswith("dash:repm:"))
async def dash_report_monthly(callback: CallbackQuery, session, lang: str) -> None:
    await _dash_send_group_report(callback, session, lang, "monthly")


@router.callback_query(F.data.startswith("dash:repy:"))
async def dash_report_yearly(callback: CallbackQuery, session, lang: str) -> None:
    await _dash_send_group_report(callback, session, lang, "yearly")


async def _dash_send_group_report(
    callback: CallbackQuery, session, lang: str, period: str
) -> None:
    chat = await _deny_dash(callback, session, lang, int(callback.data.split(":")[2]))
    if chat is None:
        return
    text = await reports_service.group_report(session, chat.id, period, lang)
    from ..services import notifier as notifier_service

    await notifier_service.send_long(callback.bot, callback.message.chat.id, text)
    await callback.answer()


@router.callback_query(F.data.startswith("dash:xlsx:"))
async def dash_export(callback: CallbackQuery, session, lang: str) -> None:
    chat = await _deny_dash(callback, session, lang, int(callback.data.split(":")[2]))
    if chat is None:
        return
    path = await exporter.build_workbook(session, chat.id, "weekly", lang)
    try:
        await callback.message.answer_document(
            BufferedInputFile(path.read_bytes(), filename=path.name)
        )
    except Exception:
        await callback.answer(t("save_error", lang), show_alert=True)
        return
    await callback.answer()


@router.callback_query(F.data.startswith("dash:settings:"))
async def dash_settings(callback: CallbackQuery, session, lang: str) -> None:
    chat = await _deny_dash(callback, session, lang, int(callback.data.split(":")[2]))
    if chat is None:
        return
    managers = await student_service.group_managers(session, chat.id)
    names = ", ".join(str(row.tg_id) for row in managers) or "—"
    await callback.message.answer(
        t("dash_settings", lang, title=_esc(chat.title or str(chat.id)),
          language=chat.language or "bi", managers=names),
        reply_markup=back_sections_kb(chat.id, lang),
    )
    await callback.answer()


@router.message(Command("assign", "biriktir"))
async def cmd_assign(
    message: Message,
    command: CommandObject,
    session,
    lang: str,
    is_teacher: bool,
    is_class: bool,
) -> None:
    if not is_class:
        await message.reply(t("only_group", lang))
        return
    if not is_teacher:
        await message.reply(t("only_teacher", lang))
        return
    args = (command.args or "").strip()
    if not args:
        await message.reply(t("assign_usage", lang))
        return
    target_id: int | None = None
    if args.lstrip("-+").isdigit():
        target_id = int(args)
    else:
        person = await student_service.find_student(session, message.chat.id, args)
        if person is not None:
            target_id = person.tg_id
    if target_id is None or target_id == message.from_user.id:
        if target_id == message.from_user.id:
            await message.reply(t("assign_self", lang))
        else:
            await message.reply(t("assign_usage", lang))
        return
    await student_service.assign_teacher(session, message.chat.id, target_id,
                                         message.from_user.id)
    await message.answer(t("assign_done", lang, name=_esc(args)))


@router.message(Command("unassign", "olib_tashla"))
async def cmd_unassign(
    message: Message,
    command: CommandObject,
    session,
    lang: str,
    is_teacher: bool,
    is_class: bool,
) -> None:
    if not is_class:
        await message.reply(t("only_group", lang))
        return
    if not is_teacher:
        await message.reply(t("only_teacher", lang))
        return
    args = (command.args or "").strip()
    if not args:
        await message.reply(t("assign_usage", lang))
        return
    target_id: int | None = None
    if args.lstrip("-+").isdigit():
        target_id = int(args)
    else:
        person = await student_service.find_student(session, message.chat.id, args)
        if person is not None:
            target_id = person.tg_id
    if target_id is None:
        await message.reply(t("assign_usage", lang))
        return
    removed = await student_service.unassign_teacher(session, message.chat.id, target_id)
    if removed:
        await message.answer(t("unassign_done", lang, name=_esc(args)))
    else:
        await message.answer(t("unassign_none", lang))


@router.message(Command("topics", "mavzular"))
async def cmd_topics(
    message: Message, session, lang: str, is_teacher: bool, is_class: bool, chat_row
) -> None:
    """Show which forum topic the bot has auto-detected for each message kind."""
    if await _say_deny(message, lang, is_teacher, is_class):
        return
    await topic_service.detect_from_message(session, chat_row, "general", message)
    lines = [t("topics_title", lang)]
    lines.append(t("topics_forum", lang) if chat_row.is_forum
                 else t("topics_not_forum", lang))
    lines.append("")
    for kind, thread in topic_service.topics_status(chat_row):
        value = (t("topics_detected", lang) if thread else t("topics_missing", lang))
        if thread:
            value = f"<code>{thread}</code> — {value}"
        lines.append(t("topics_status", lang,
                       kind=topic_service.KIND_LABEL.get(kind, kind), value=value))
    lines.append(t("topics_how", lang))
    await message.answer("\n".join(lines))


@router.message(Command("attendance", "davomat"))
async def cmd_attendance(
    message: Message, session, lang: str, is_teacher: bool, is_class: bool
) -> None:
    if await _say_deny(message, lang, is_teacher, is_class):
        return
    students = await student_service.list_students(session, message.chat.id)
    if not students:
        await message.reply(t("att_none", lang))
        return
    day = today()
    rows = await attendance_service.for_day(session, message.chat.id, day)
    marks = {sid: row.status for sid, row in rows.items()}
    text = f"{t('att_title', lang, date=fmt_date_short(day))}\n{t('att_help', lang)}"
    await message.answer(text, reply_markup=attendance_kb(students, marks, lang, message.chat.id))


def _attendance_target(callback: CallbackQuery) -> tuple[int, int]:
    """Parse `att:*:{chat_id}:{tg_id}` — chat_id 0 means "use this chat".

    Older keyboards carried only `att:*:{tg_id}` (and the bulk buttons used a
    word instead of a number), so both layouts are tolerated.
    """
    parts = callback.data.split(":")
    if len(parts) >= 4 and parts[3].lstrip("-").isdigit():
        return int(parts[2]), int(parts[3])
    if len(parts) >= 3 and parts[2].lstrip("-").isdigit():
        return callback.message.chat.id, int(parts[2])
    return callback.message.chat.id, 0


async def _refresh_attendance(session, chat_id: int, lang: str, message: Message) -> dict:
    students = await student_service.list_students(session, chat_id)
    rows = await attendance_service.for_day(session, chat_id, today())
    marks = {sid: row.status for sid, row in rows.items()}
    try:
        await message.edit_reply_markup(
            reply_markup=attendance_kb(students, marks, lang, chat_id)
        )
    except Exception:
        pass
    return marks


@router.callback_query(F.data.startswith("att:cycle:"))
async def att_cycle(
    callback: CallbackQuery, session, lang: str, is_teacher: bool
) -> None:
    if not is_teacher:
        await callback.answer(t("only_teacher", lang), show_alert=True)
        return
    chat_id, student_id = _attendance_target(callback)
    if chat_id == 0:
        chat_id = callback.message.chat.id
    day = today()
    rows = await attendance_service.for_day(session, chat_id, day)
    current = rows[student_id].status if student_id in rows else None
    new_status = attendance_service.CYCLE[current] if current else "absent"
    await attendance_service.set_status(
        session, chat_id, student_id, day, new_status, callback.from_user.id
    )
    points = await scoring.attendance_points(
        session, chat_id, student_id, new_status, day.isoformat()
    )
    await _refresh_attendance(session, chat_id, lang, callback.message)
    student = await student_service.get_user(session, chat_id, student_id)
    await callback.answer(
        t("att_saved", lang,
          name=(student.full_name if student else str(student_id)),
          status=attendance_status_label(new_status, lang),
          points=points)
    )


@router.callback_query(F.data.startswith("att:all:"))
async def att_all(callback: CallbackQuery, session, lang: str, is_teacher: bool) -> None:
    if not is_teacher:
        await callback.answer(t("only_teacher", lang), show_alert=True)
        return
    chat_id, _ = _attendance_target(callback)
    if chat_id == 0:
        chat_id = callback.message.chat.id
    students = await student_service.list_students(session, chat_id)
    for student in students:
        await attendance_service.set_status(
            session, chat_id, student.tg_id, today(), "present", callback.from_user.id
        )
    await _refresh_attendance(session, chat_id, lang, callback.message)
    await callback.answer(t("done", lang))


@router.callback_query(F.data.startswith("att:done:"))
async def att_done(callback: CallbackQuery, session, lang: str, is_teacher: bool) -> None:
    if not is_teacher:
        await callback.answer(t("only_teacher", lang), show_alert=True)
        return
    chat_id, _ = _attendance_target(callback)
    if chat_id == 0:
        chat_id = callback.message.chat.id
    rows = await attendance_service.for_day(session, chat_id, today())
    marked = len(rows)
    await callback.message.answer(
        f"{t('att_finished', lang, date=fmt_date_short(today()))} ({marked})"
    )
    await callback.answer()


WEEKDAYS = {
    "monday": 0, "mon": 0, "dushanba": 0,
    "tuesday": 1, "tue": 1, "seshanba": 1,
    "wednesday": 2, "wed": 2, "chorshanba": 2,
    "thursday": 3, "thu": 3, "payshanba": 3,
    "friday": 4, "fri": 4, "juma": 4,
    "saturday": 5, "sat": 5, "shanba": 5,
    "sunday": 6, "sun": 6, "yakshanba": 6,
}


@router.message(Command("timetable", "jadval"))
async def cmd_timetable(
    message: Message,
    command: CommandObject,
    session,
    lang: str,
    is_teacher: bool,
    is_class: bool,
) -> None:
    if await _say_deny(message, lang, is_teacher, is_class):
        return
    args = (command.args or "").split()
    if args and args[0].lower() in {"add", "qosh", "qo'sh", "set"}:
        if len(args) < 3:
            await message.reply(t("tt_usage", lang))
            return
        index = WEEKDAYS.get(args[1].lower())
        if index is None:
            await message.reply(t("tt_bad_weekday", lang))
            return
        parsed = parse_time(args[2])
        if parsed is None:
            await message.reply(t("tt_usage", lang))
            return
        await schedule_service.add_slot(session, message.chat.id, index, args[2])
        await message.reply(
            t("tt_added", lang, weekday=fmt_weekday(index), time=parsed.strftime("%H:%M"))
        )
        return
    if args and args[0].lower() in {"clear", "del", "ochir", "o'chir"}:
        if len(args) > 1 and args[1].lstrip("#").isdigit():
            removed = await schedule_service.remove_slot(
                session, message.chat.id, int(args[1].lstrip("#"))
            )
            await message.reply(t("tt_removed", lang) if removed else t("tt_usage", lang))
            return
        count = await schedule_service.clear_slots(session, message.chat.id)
        await message.reply(f"{t('tt_removed', lang)} ({count})")
        return

    slots = await schedule_service.list_slots(session, message.chat.id)
    lines = [t("tt_title", lang), ""]
    if slots:
        for slot in slots:
            lines.append(f"#{slot.id} · {fmt_weekday(slot.weekday)} — {slot.start_time}")
    else:
        lines.append(t("tt_empty", lang, hours=settings.default_due_hours))
    next_lesson = await schedule_service.next_lesson(session, message.chat.id)
    if next_lesson:
        lines.append("")
        lines.append(t("tt_next", lang, when=fmt_datetime(next_lesson)))
    lines.append("")
    lines.append(t("tt_usage", lang))
    await message.answer("\n".join(lines))


@router.message(Command("pending", "navbat"))
async def cmd_pending(
    message: Message, session, lang: str, is_teacher: bool, is_class: bool
) -> None:
    if await _say_deny(message, lang, is_teacher, is_class):
        return
    rows = await submission_service.pending(session, message.chat.id)
    if not rows:
        await message.reply(t("pen_pending_none", lang))
        return
    students = {s.tg_id: s for s in await student_service.list_students(session, message.chat.id)}
    homeworks: dict[int, object] = {}
    lines = [t("pen_pending_title", lang), ""]
    for row in rows:
        student = students.get(row.student_id)
        if row.homework_id not in homeworks:
            homeworks[row.homework_id] = await homework_service.get(session, row.homework_id)
        homework = homeworks[row.homework_id]
        lines.append(
            t("pen_sub_line", lang, id=row.id,
              name=notifier.esc(student.full_name) if student else str(row.student_id),
              title=notifier.esc(getattr(homework, "title", "—")),
              when=fmt_datetime(row.submitted_at))
        )
    await message.answer("\n".join(lines),
                         reply_markup=pending_kb([row.id for row in rows], lang))


async def _apply_manual(
    session,
    submission,
    score: int,
    comment: str,
    graded_by: int,
    verdict: str | None = None,
) -> float:
    """Save a manual grade and re-award points (idempotent per submission)."""
    if verdict is None:
        verdict = "correct" if score >= 80 else "partial" if score >= 50 else "wrong"
    await submission_service.set_manual(session, submission, score, comment or "", graded_by)
    points, kind = scoring.points_for(score, verdict, submission.is_late)
    await scoring.award(
        session,
        submission.chat_id,
        submission.student_id,
        kind,
        points,
        f"Teacher review #{submission.id}",
        homework_id=submission.homework_id,
        created_by=graded_by,
        event_key=f"sub:{submission.id}",
    )
    await submission_service.set_points(session, submission, points)
    submission.ai_verdict = verdict
    await session.flush()
    return points


@router.message(Command("grade"))
async def cmd_grade(
    message: Message,
    command: CommandObject,
    session,
    lang: str,
    is_teacher: bool,
    is_class: bool,
) -> None:
    if await _say_deny(message, lang, is_teacher, is_class):
        return
    parts = (command.args or "").split(maxsplit=2)
    if len(parts) < 2 or not parts[0].isdigit() or not parts[1].lstrip("-").isdigit():
        await message.reply(t("pen_grade_usage", lang))
        return
    submission = await submission_service.get_by_id(session, int(parts[0]))
    if submission is None:
        await message.reply(t("pen_pending_none", lang))
        return
    score = max(0, min(100, int(parts[1])))
    comment = parts[2] if len(parts) > 2 else ""
    points = await _apply_manual(session, submission, score, comment, message.from_user.id)
    await message.reply(t("pen_graded", lang, id=submission.id, score=score, points=points))


@router.callback_query(F.data.startswith("sub:grade:"))
async def sub_grade_start(
    callback: CallbackQuery, state: FSMContext, lang: str, is_teacher: bool
) -> None:
    if not is_teacher:
        await callback.answer(t("only_teacher", lang), show_alert=True)
        return
    submission_id = int(callback.data.split(":")[2])
    await state.set_state(ManualGrade.score)
    await state.update_data(submission_id=submission_id)
    await callback.message.answer(t("pen_grade_usage", lang) + f"\n#{submission_id}")
    await callback.answer()


@router.message(ManualGrade.score, F.text)
async def manual_score(message: Message, state: FSMContext, session, lang: str, bot: Bot) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if not parts or not parts[0].lstrip("-").isdigit():
        await message.answer(t("pen_grade_usage", lang))
        return
    data = await state.get_data()
    submission = await submission_service.get_by_id(session, int(data.get("submission_id") or 0))
    if submission is None:
        await state.clear()
        await message.answer(t("pen_pending_none", lang))
        return
    score = max(0, min(100, int(parts[0])))
    comment = parts[1] if len(parts) > 1 else ""
    points = await _apply_manual(session, submission, score, comment, message.from_user.id)
    await state.clear()
    student = await student_service.get_user(session, submission.chat_id, submission.student_id)
    homework = await homework_service.get(session, submission.homework_id)
    await message.answer(t("pen_graded", lang, id=submission.id, score=score, points=points))
    if student is not None:
        await notifier.send_feedback(bot, submission, homework, student, points, lang)


@router.callback_query(F.data.startswith("sub:"))
async def sub_review(
    callback: CallbackQuery, session, lang: str, is_teacher: bool
) -> None:
    """Teacher override of an AI verdict: accept / partial / reject."""
    if not is_teacher:
        await callback.answer(t("only_teacher", lang), show_alert=True)
        return
    parts = callback.data.split(":")
    if len(parts) != 3 or not parts[2].isdigit():
        await callback.answer()
        return
    action = parts[1]
    submission = await submission_service.get_by_id(session, int(parts[2]))
    if submission is None:
        await callback.answer(t("pen_pending_none", lang), show_alert=True)
        return
    if action == "accept":
        score, verdict = submission.ai_score, submission.ai_verdict or "correct"
    elif action == "partial":
        score, verdict = submission.ai_score, "partial"
    elif action == "reject":
        score, verdict = 0, "wrong"
    else:
        await callback.answer()
        return
    points = await _apply_manual(
        session, submission, score, submission.teacher_comment, callback.from_user.id, verdict
    )
    await callback.answer(
        t("pen_graded", lang, id=submission.id, score=score, points=points)
    )


@router.message(Command("bonus", "penalty"))
async def cmd_points(
    message: Message,
    command: CommandObject,
    session,
    lang: str,
    is_teacher: bool,
    is_class: bool,
) -> None:
    if await _say_deny(message, lang, is_teacher, is_class):
        return
    key = "pen_bonus_usage" if command.command == "bonus" else "pen_penalty_usage"
    args = (command.args or "").split(maxsplit=2)
    if len(args) < 2:
        await message.reply(t(key, lang))
        return
    try:
        amount = abs(float(args[1].replace(",", ".")))
    except ValueError:
        await message.reply(t(key, lang))
        return
    student = await student_service.find_student(session, message.chat.id, args[0])
    if student is None:
        await message.reply(t("student_unknown", lang))
        return
    sign = -1 if command.command == "penalty" else 1
    reason = args[2] if len(args) > 2 else ("bonus" if sign > 0 else "penalty")
    await scoring.manual(session, message.chat.id, student.tg_id, sign * amount, reason,
                         message.from_user.id)
    total = await scoring.total(session, message.chat.id, student.tg_id)
    await message.answer(
        t("pen_points_added", lang, name=notifier.esc(student.full_name),
          sign="+" if sign > 0 else "-", points=amount, reason=notifier.esc(reason))
        + f"\n🏅 total: {total}"
    )


@router.message(Command("extra"))
async def cmd_extra(
    message: Message,
    command: CommandObject,
    session,
    lang: str,
    is_teacher: bool,
    is_class: bool,
) -> None:
    if await _say_deny(message, lang, is_teacher, is_class):
        return
    args = (command.args or "").split(maxsplit=1)
    if len(args) < 2:
        await message.reply(t("pen_extra_usage", lang))
        return
    student = await student_service.find_student(session, message.chat.id, args[0])
    if student is None:
        await message.reply(t("student_unknown", lang))
        return
    await scoring.assign_extra(session, message.chat.id, student.tg_id, args[1],
                               message.from_user.id)
    await message.answer(
        t("pen_extra_assigned", lang, name=notifier.esc(student.full_name), hours=48,
          task=notifier.esc(args[1]))
    )




