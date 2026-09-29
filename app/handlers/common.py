"""Shared commands: start, help, language, diagnostics, roster, cancel."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import ChatMemberUpdated, Message

from ..ai_worker import get_worker
from ..config import settings
from ..deeplink import parse_parent_payload
from ..i18n import lang_display, normalize_lang, t
from ..keyboards import groups_kb, miniapp_kb, student_menu_kb
from ..services import homework as homework_service
from ..services import reports as reports_service
from ..services import schedule as schedule_service
from ..services import students as student_service
from ..services.notifier import esc as notifier_esc
from ..utils import now


async def _can_manage(session, chat_id: int, user_id: int) -> bool:
    """True when the person may open this group (settings + any DB role)."""
    if settings.is_admin(user_id) or settings.is_teacher(user_id):
        return True
    user = await student_service.get_user(session, chat_id, user_id)
    if user is not None and user.role in {"teacher", "admin"}:
        return True
    chats = {chat.id for chat in await student_service.teacher_chats(session, user_id)}
    return chat_id in chats


async def _open_parent_link(message: Message, session, lang: str) -> bool:
    """Handle ?start=parent_<chat>_<student>. True when a link was opened."""
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        return False
    payload = args[1].strip()
    if not payload.startswith("parent_"):
        return False
    parsed = parse_parent_payload(payload)
    if parsed is None:
        await message.answer(t("parent_link_unknown", lang))
        return True
    chat_id, student_id = parsed
    if not await _can_manage(session, chat_id, message.from_user.id):
        await message.answer(t("parent_link_denied", lang))
        return True
    student = await student_service.get_user(session, chat_id, student_id)
    if student is None:
        await message.answer(t("student_unknown", lang))
        return True
    text, _ = await reports_service.student_report(session, chat_id, student,
                                                   "weekly", lang)
    await message.answer(t("parent_link_sent", lang))
    await message.answer(text)
    return True


async def _dashboard_groups_text(session, chats, lang: str) -> str:
    """One shared dashboard header used from /start and /menu."""
    lines = [t("menu_dashboard", lang), "", t("dash_pick_group", lang), ""]
    for chat in chats:
        students = await student_service.count_students(session, chat.id)
        active = await homework_service.count_active(session, chat.id)
        lines.append(
            f"🏫 <b>{notifier_esc(chat.title or str(chat.id))}</b>\n"
            f"   {t('dash_group_line', lang, students=students, active=active)}"
        )
    return "\n".join(lines)

router = Router(name="common")


@router.my_chat_member()
async def on_bot_added(event: ChatMemberUpdated, session, lang: str) -> None:
    """Greet the group when the bot is added, and remember forum mode."""
    if event.new_chat_member.status in {"member", "administrator"} and (
        event.old_chat_member.status in {"left", "kicked"}
    ):
        chat_row = await student_service.get_chat(
            session, event.chat.id, event.chat.title
        )
        chat_row.is_forum = bool(getattr(event.chat, "is_forum", False))
        await session.flush()
        try:
            await event.bot.send_message(event.chat.id, t("welcome_group", lang))
        except Exception:
            pass


@router.chat_member()
async def on_member_join(event: ChatMemberUpdated, session, lang: str) -> None:
    """Everyone who joins the group becomes a student automatically.

    Teachers are the exception: the ids in ADMIN_IDS / TEACHER_IDS are
    registered as staff instead, so they never show up in the student roster.
    """
    if event.chat.type not in {"group", "supergroup"}:
        return
    user = event.new_chat_member.user
    if user.is_bot:
        return
    was_member = event.old_chat_member.status in {
        "member", "administrator", "creator", "restricted",
    }
    is_member = event.new_chat_member.status in {"member", "administrator", "creator"}
    if not is_member:
        if was_member:  # left / was removed → pause their data
            await student_service.set_active(session, event.chat.id, user.id, False)
        return
    if was_member:
        await student_service.set_active(session, event.chat.id, user.id, True)
        return
    await student_service.get_chat(session, event.chat.id, event.chat.title)
    account = await student_service.touch_user(
        session, user.id, event.chat.id, user.full_name, user.username,
        settings.is_teacher(user.id) or settings.is_admin(user.id),
    )
    if account.role == "student":
        try:
            await event.bot.send_message(
                event.chat.id, t("student_joined", lang, name=notifier_esc(user.full_name))
            )
        except Exception:
            pass


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    session,
    lang: str,
    is_class: bool,
    is_teacher: bool,
) -> None:
    if is_class:
        await message.reply(t("welcome_group", lang))
        if not is_teacher:
            await message.answer(t("help_student", lang))
        return
    # A parent's deep link: /start parent_<chat>_<student>
    opened = await _open_parent_link(message, session, lang)
    if opened:
        return
    name = message.from_user.full_name if message.from_user else "friend"
    await message.answer(
        t("welcome_private", lang, name=name), reply_markup=student_menu_kb(lang)
    )
    if is_teacher:
        chats = await student_service.teacher_chats(session, message.from_user.id)
        if chats:
            text = await _dashboard_groups_text(session, chats, lang)
            await message.answer(text, reply_markup=groups_kb(chats, lang))
        await message.answer(t("help_teacher", lang))


@router.message(Command("help"))
async def cmd_help(message: Message, lang: str, is_teacher: bool, is_class: bool) -> None:
    text = t("help_teacher" if is_teacher else "help_student", lang)
    if is_teacher and not is_class:
        text += "\n\n" + t("check_privacy", lang)
    await message.answer(f"{t('help_title', lang)}\n\n{text}")


@router.message(Command("menu"))
async def cmd_menu(
    message: Message, session, lang: str, is_teacher: bool, is_class: bool
) -> None:
    if is_teacher and not is_class:
        chats = await student_service.teacher_chats(session, message.from_user.id)
        if chats:
            text = await _dashboard_groups_text(session, chats, lang)
            await message.answer(text, reply_markup=groups_kb(chats, lang))
            return
        await message.answer(t("help_teacher", lang))
    elif is_class:
        await message.answer(t("help_student", lang))
    else:
        await message.answer(t("menu_title", lang), reply_markup=student_menu_kb(lang))


@router.message(Command("language"))
async def cmd_language(
    message: Message,
    command: CommandObject,
    session,
    lang: str,
    is_teacher: bool,
    is_class: bool,
    chat_row,
) -> None:
    if not is_teacher:
        await message.reply(t("only_teacher", lang))
        return
    if not is_class:
        await message.reply(t("only_group", lang))
        return
    raw = (command.args or "").strip()
    if not raw:
        current = chat_row.language if chat_row else lang
        await message.answer(
            f"{t('check_lang', lang, lang=lang_display(current))}\n\n{t('lang_usage', lang)}"
        )
        return
    new_lang = normalize_lang(raw)
    await student_service.set_language(session, message.chat.id, new_lang)
    await message.answer(t("lang_set", lang, name=lang_display(new_lang)))


@router.message(Command("id"))
async def cmd_id(message: Message, lang: str) -> None:
    await message.reply(
        t("id_info", lang, user_id=message.from_user.id, chat_id=message.chat.id)
    )


@router.message(Command("now"))
async def cmd_now(message: Message) -> None:
    await message.reply(now().strftime("%d.%m.%Y %H:%M"))


@router.message(Command("app", "panel"))
async def cmd_app(
    message: Message,
    session,
    lang: str,
    is_teacher: bool,
) -> None:
    """Open the teacher dashboard: one tap per group from private chat."""
    if not is_teacher:
        await message.reply(t("only_teacher", lang))
        return
    if not settings.miniapp_ready:
        await message.reply(t("app_open_off", lang))
        return
    chats = await student_service.teacher_chats(session, message.from_user.id)
    if not chats:
        await message.reply(t("app_open_off", lang))
        return
    base = (settings.miniapp_public_url or
            f"http://{settings.miniapp_host}:{settings.miniapp_port}").rstrip("/")
    if base.startswith("http://"):
        await message.answer(t("app_open_https", lang, url=base + "/"))
        return
    for chat in chats:
        url = (f"{base}/?chat={chat.id}&token={settings.miniapp_token}")
        await message.answer(
            t("app_chat_title", lang, title=notifier_esc(chat.title or str(chat.id))),
            reply_markup=miniapp_kb(url, lang),
        )


@router.message(Command("check"))
async def cmd_check(message: Message, session, lang: str, is_teacher: bool) -> None:
    if not is_teacher:
        await message.reply(t("only_teacher", lang))
        return
    students = await student_service.count_students(session, message.chat.id)
    slots = await schedule_service.list_slots(session, message.chat.id)
    active = await homework_service.count_active(session, message.chat.id)
    next_lesson = await schedule_service.next_lesson(session, message.chat.id)
    lines = [t("check_title", lang)]
    lines.append(
        t("check_ai_on", lang, model=settings.ai_model)
        if settings.ai_ready
        else t("check_ai_off", lang)
    )
    try:
        worker = get_worker()
        lines.append(t("check_worker", lang, queue=worker.queue_size,
                       done=worker.processed, failed=worker.failed))
    except RuntimeError:
        pass  # worker not started (e.g. inside tests)
    lines.append(t("check_schedule", lang, count=len(slots)))
    lines.append(t("check_students", lang, count=students))
    lines.append(t("check_active", lang, count=active))
    lines.append(t("check_lang", lang, lang=lang_display(lang)))
    lines.append(
        t("tt_next", lang, when=next_lesson.strftime("%d.%m.%Y %H:%M"))
        if next_lesson
        else t("tt_empty", lang, hours=settings.default_due_hours)
    )
    lines.append("")
    lines.append(t("check_privacy", lang))
    await message.answer("\n".join(lines))


@router.message(Command("roster"))
async def cmd_roster(
    message: Message,
    command: CommandObject,
    session,
    lang: str,
    is_teacher: bool,
    chat_row,
) -> None:
    if not is_teacher:
        await message.reply(t("only_teacher", lang))
        return
    args = (command.args or "").split(maxsplit=1)
    if len(args) == 2:
        action, target = args[0].lower(), args[1]
        student = await student_service.find_student(session, message.chat.id, target)
        if student is None:
            await message.reply(t("student_unknown", lang))
            return
        if action in {"teacher", "student"}:
            await student_service.set_role(session, message.chat.id, student.tg_id, action)
            await message.answer(
                t("roster_promoted", lang, name=student.full_name,
                  role=t(f"roster_role_{action}", lang))
            )
            return
        if action in {"remove", "delete"}:
            await student_service.set_active(session, message.chat.id, student.tg_id, False)
            await message.answer(t("done", lang))
            return
        await message.answer(t("roster_usage", lang))
        return

    users = await student_service.all_users(session, message.chat.id)
    if not users:
        await message.answer(t("roster_empty", lang))
        return
    lines = [t("roster_title", lang), t("roster_auto", lang), ""]
    for user in users:
        role_key = f"roster_role_{user.role}" if user.role in {"teacher", "student"} \
            else "roster_role_student"
        extra = f" (@{user.username})" if user.username else ""
        if not user.is_active:
            extra += " — ⛔"
        lines.append(t("roster_line", lang, name=user.full_name,
                       role=t(role_key, lang), extra=extra))
    lines.append("")
    lines.append(t("roster_usage", lang))
    await message.answer("\n".join(lines))


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, lang: str) -> None:
    await state.clear()
    await message.reply(t("cancelled", lang))
