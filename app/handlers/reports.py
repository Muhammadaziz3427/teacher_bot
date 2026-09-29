"""Report commands: weekly, monthly, yearly, per-student and Excel export.

Student reports are **private**: when a teacher asks for them the bot delivers
them to the teacher's private chat (never into the class group). Add the word
``group`` to a command when a summary really should be posted in the group.
"""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from ..config import settings
from ..deeplink import build_parent_payload, parent_url
from ..i18n import t
from ..keyboards import parent_link_kb, report_kb, students_kb
from ..services import exporter
from ..services import notifier
from ..services import reports as reports_service
from ..services import students as student_service
from ..services import topics as topic_service

router = Router(name="reports")


async def _send_private(bot: Bot, teacher_id: int, text: str, kb=None) -> bool:
    """Deliver a report to a teacher's DM; False when they never pressed /start."""
    try:
        if kb is not None:
            await notifier.send_long(bot, teacher_id, text, reply_markup=kb)
        else:
            await notifier.send_long(bot, teacher_id, text)
        return True
    except Exception:
        return False


async def _send_all_reports(
    bot: Bot,
    session,
    chat_id: int,
    teacher_id: int,
    lang: str,
    periods: tuple[str, ...] = ("weekly", "monthly"),
) -> tuple[int, int]:
    """Every student, every period — straight into the teacher's private chat."""
    students = await student_service.list_students(session, chat_id)
    sent = failed = 0
    for student in students:
        for period in periods:
            text, _ = await reports_service.student_report(
                session, chat_id, student, period, lang
            )
            if await _send_private(bot, teacher_id, text):
                sent += 1
            else:
                failed += 1
    return sent, failed


@router.message(Command("weekly", "monthly", "yearly", "haftalik", "oylik", "yillik"))
async def cmd_report(
    message: Message,
    command: CommandObject,
    session,
    lang: str,
    is_teacher: bool,
    is_class: bool,
    chat_row,
) -> None:
    if not is_class:
        await message.reply(t("only_group", lang))
        return
    period = {
        "weekly": "weekly", "haftalik": "weekly",
        "monthly": "monthly", "oylik": "monthly",
        "yearly": "yearly", "yillik": "yearly",
    }.get(command.command, "weekly")
    args = (command.args or "").strip()
    words = args.lower().split()
    to_group = "group" in words or "guruh" in words
    everything = "all" in words or "hammasi" in words

    if is_teacher and not to_group:
        # Reports belong to the teacher only — send them privately.
        await topic_service.detect_from_message(session, chat_row, "announcements", message)
        if everything or not args:
            await message.reply(
                t("rep_all_started", lang, count=await student_service.count_students(
                    session, message.chat.id))
            )
            sent, failed = await _send_all_reports(
                message.bot, session, message.chat.id, message.from_user.id, lang,
                periods=(period,),
            )
            if sent:
                await message.reply(t("rep_all_done", lang, count=sent))
            if failed and not sent:
                await message.reply(t("rep_private_needed", lang))
            return
        student = await student_service.find_student(session, message.chat.id, args)
        if student is None:
            await message.reply(t("student_unknown", lang))
            return
        text, _ = await reports_service.student_report(
            session, message.chat.id, student, period, lang
        )
        if await _send_private(
            message.bot, message.from_user.id, text,
            report_kb(message.chat.id, student.tg_id, period, lang),
        ):
            await message.reply(t("rep_private_sent", lang, count=1))
        else:
            await message.reply(t("rep_private_needed", lang))
        return

    if is_teacher and to_group:
        text = await reports_service.group_report(session, message.chat.id, period, lang)
        await notifier.send_long(
            message.bot, message.chat.id, text,
            thread_id=topic_service.thread_for(chat_row, "announcements"),
        )
        return

    # students see their own report
    student = await student_service.get_user(session, message.chat.id, message.from_user.id)
    if student is None:
        await message.reply(t("st_no_class", lang))
        return
    text, _ = await reports_service.student_report(
        session, message.chat.id, student, period, lang
    )
    await notifier.send_long(message.bot, message.chat.id, text)


@router.message(Command("report", "hisobot"))
async def cmd_single_report(
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
    words = args.lower().split()
    if not args:
        await message.reply(t("rep_usage", lang))
        return
    if words and words[0] in {"all", "hammasi"}:
        await message.reply(
            t("rep_all_started", lang,
              count=await student_service.count_students(session, message.chat.id))
        )
        sent, failed = await _send_all_reports(
            message.bot, session, message.chat.id, message.from_user.id, lang
        )
        if sent:
            await message.reply(t("rep_all_done", lang, count=sent))
        if failed and not sent:
            await message.reply(t("rep_private_needed", lang))
        return
    student = await student_service.find_student(session, message.chat.id, args)
    if student is None:
        await message.reply(t("student_unknown", lang))
        return
    text, _ = await reports_service.student_report(
        session, message.chat.id, student, "weekly", lang
    )
    if await _send_private(
        message.bot, message.from_user.id, text,
        report_kb(message.chat.id, student.tg_id, "weekly", lang),
    ):
        await message.reply(t("rep_private_sent", lang, count=1))
    else:
        await message.reply(t("rep_private_needed", lang))


@router.message(Command("ranking", "rejting"))
async def cmd_ranking(
    message: Message,
    command: CommandObject,
    session,
    lang: str,
    is_teacher: bool,
    is_class: bool,
    chat_row,
) -> None:
    if not is_class:
        await message.reply(t("only_group", lang))
        return
    args = (command.args or "").strip().lower().split()
    to_group = "group" in args or "guruh" in args
    period = {"monthly": "monthly", "oylik": "monthly",
              "yearly": "yearly", "yillik": "yearly"}.get(
        next((word for word in args if word not in {"group", "guruh"}), "weekly"),
        "weekly",
    )
    text = await reports_service.ranking(session, message.chat.id, period, lang)
    if is_teacher and not to_group:
        if await _send_private(message.bot, message.from_user.id, text):
            await message.reply(t("rep_private_sent", lang, count=1))
        else:
            await message.reply(t("rep_private_needed", lang))
        return
    await notifier.send_long(
        message.bot, message.chat.id, text,
        thread_id=topic_service.thread_for(chat_row, "announcements"),
    )


@router.message(Command("export", "excel"))
async def cmd_export(
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
    period = {"monthly": "monthly", "oylik": "monthly", "yearly": "yearly",
              "yillik": "yearly"}.get((command.args or "").strip().lower(), "weekly")
    path = await exporter.build_workbook(session, message.chat.id, period, lang)
    document = BufferedInputFile(path.read_bytes(), filename=path.name)
    try:  # the workbook is class data: keep it private
        await message.bot.send_document(message.from_user.id, document)
        await message.reply(t("rep_private_sent", lang, count=1))
    except Exception:
        await message.reply(t("rep_private_needed", lang))


@router.callback_query(F.data.startswith("rep:period:"))
async def rep_period(callback: CallbackQuery, session, lang: str) -> None:
    _, _, raw_chat, period, raw_id = callback.data.split(":")
    chat_id = int(raw_chat)
    student_id = int(raw_id)
    if student_id == 0:
        text = await reports_service.group_report(session, chat_id, period, lang)
        await notifier.send_long(callback.bot, chat_id, text)
        await callback.answer()
        return
    student = await student_service.get_user(session, chat_id, student_id)
    if student is None:
        await callback.answer(t("student_unknown", lang), show_alert=True)
        return
    text, _ = await reports_service.student_report(session, chat_id, student, period, lang)
    await notifier.send_long(
        callback.bot, callback.from_user.id, text,
        reply_markup=report_kb(chat_id, student_id, period, lang),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("rep:export:"))
async def rep_export(
    callback: CallbackQuery, session, lang: str, is_teacher: bool
) -> None:
    if not is_teacher:
        await callback.answer(t("only_teacher", lang), show_alert=True)
        return
    _, _, raw_chat, period, _raw = callback.data.split(":")
    path = await exporter.build_workbook(session, int(raw_chat), period, lang)
    document = BufferedInputFile(path.read_bytes(), filename=path.name)
    await callback.message.answer_document(document)
    await callback.answer(t("rep_export_ready", lang, name=path.name))


@router.callback_query(F.data.startswith("rep:pick:"))
async def rep_pick(callback: CallbackQuery, session, lang: str) -> None:
    _, _, raw_chat, period, _raw = callback.data.split(":")
    chat_id = int(raw_chat)
    students = await student_service.list_students(session, chat_id)
    if not students:
        await callback.answer(t("rep_nobody", lang), show_alert=True)
        return
    await callback.message.answer(
        t("rep_pick_student", lang),
        reply_markup=students_kb(students, "rep:student", lang, period, chat_id=chat_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("rep:student:"))
async def rep_student(callback: CallbackQuery, session, lang: str) -> None:
    _, _, raw_chat, period, raw_id = callback.data.split(":")
    chat_id = int(raw_chat)
    student = await student_service.get_user(session, chat_id, int(raw_id))
    if student is None:
        await callback.answer(t("student_unknown", lang), show_alert=True)
        return
    text, _ = await reports_service.student_report(session, chat_id, student, period, lang)
    await notifier.send_long(
        callback.bot, callback.from_user.id, text,
        reply_markup=report_kb(chat_id, student.tg_id, period, lang),
    )
    await callback.answer()


@router.message(Command("parent", "otaona"))
async def cmd_parent_copy(
    message: Message,
    command: CommandObject,
    session,
    lang: str,
    is_teacher: bool,
    is_class: bool,
) -> None:
    """Send the parent-ready copy to the teacher so they can forward it."""
    if not is_class:
        await message.reply(t("only_group", lang))
        return
    if not is_teacher:
        await message.reply(t("only_teacher", lang))
        return
    args = (command.args or "").strip()
    if not args or args.lower().split()[0] in {"all", "hammasi"}:
        await message.reply(t("rep_usage", lang))
        return
    student = await student_service.find_student(session, message.chat.id, args)
    if student is None:
        await message.reply(t("student_unknown", lang))
        return
    text, _ = await reports_service.student_report(
        session, message.chat.id, student, "weekly", lang
    )
    header = "\n\n" + t("rep_parent_format", lang)
    if await _send_private(message.bot, message.from_user.id, text + header):
        await message.reply(t("rep_private_sent", lang, count=1))
    else:
        await message.reply(t("rep_private_needed", lang))


@router.message(Command("link", "havola"))
async def cmd_parent_link(
    message: Message,
    command: CommandObject,
    session,
    lang: str,
    is_teacher: bool,
    is_class: bool,
) -> None:
    """One-tap deep link for the parent: t.me/<bot>?start=parent_<chat>_<id>."""
    if not is_class:
        await message.reply(t("only_group", lang))
        return
    if not is_teacher:
        await message.reply(t("only_teacher", lang))
        return
    args = (command.args or "").strip()
    if not args or args.lower().split()[0] in {"all", "hammasi"}:
        await message.reply(t("rep_usage", lang))
        return
    student = await student_service.find_student(session, message.chat.id, args)
    if student is None:
        await message.reply(t("student_unknown", lang))
        return

    username = settings.bot_username
    if not username:
        try:
            username = (await message.bot.me()).username or ""
        except Exception:
            username = ""
    url = parent_url(username, message.chat.id, student.tg_id)
    if not url:
        await message.reply(t("parent_link_no_username", lang))
        return
    payload = build_parent_payload(message.chat.id, student.tg_id)
    await message.answer(
        t("parent_link_ready", lang) + f"\n<code>/start {payload}</code>",
        reply_markup=parent_link_kb(url, lang),
    )
