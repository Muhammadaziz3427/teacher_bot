"""Student side: submitting homework and personal stats."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import BaseFilter, Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ..ai_worker import CheckJob, get_worker
from ..config import settings
from ..i18n import t
from ..keyboards import submission_confirm_kb
from ..services import homework as homework_service
from ..services import notifier
from ..services import scoring
from ..services import students as student_service
from ..services import submissions as submission_service
from ..services import attendance as attendance_service
from ..services import reports as reports_service
from ..states import StudentSubmit
from ..utils import fmt_date_short, fmt_datetime, truncate
from .. import stt

router = Router(name="student")

MAX_IMAGES = 3


async def _collect_images(bot: Bot, message: Message) -> list[tuple[bytes, str]]:
    """Download up to MAX_IMAGES photos/documents from the message."""
    uploads: list[tuple[str, str]] = []
    if message.photo:
        uploads.append((message.photo[-1].file_id, "image/jpeg"))
    if message.document and (message.document.mime_type or "").startswith("image/"):
        uploads.append((message.document.file_id, message.document.mime_type or "image/jpeg"))
    images: list[tuple[bytes, str]] = []
    for file_id, mime in uploads[:MAX_IMAGES]:
        try:
            buffer = await bot.download(file_id)
            if buffer is not None:
                images.append((buffer.read(), mime))
        except Exception:
            continue
    return images


async def _resolve_homework(session, message: Message, state: FSMContext):
    """Find the homework being answered: chosen id, reply target, or the latest."""
    data = await state.get_data()
    chosen = data.get("homework_id")
    if chosen:
        found = await homework_service.get(session, int(chosen), message.chat.id)
        if found is not None:
            return found
    if message.reply_to_message is not None:
        found = await homework_service.by_message(
            session, message.chat.id, message.reply_to_message.message_id
        )
        if found is not None:
            return found
    return await homework_service.latest_active(session, message.chat.id)


async def _voice_to_text(bot: Bot, message: Message, lang: str) -> tuple[str, str, str]:
    """Return (transcript, file_id, media_type) for a voice answer.

    A failed download or a missing key yields an empty transcript — but the
    student always gets a reply explaining what went wrong, so nothing feels
    like it vanished into the void.
    """
    voice = message.voice
    if voice is None:  # video notes / audio files do not count as homework
        return "", None, "text"
    if stt.too_large(voice.file_size):
        await message.reply(t("voice_too_big", lang))
        return "", None, "text"
    if not stt.is_voice_ready():
        await message.reply(t("voice_not_ready", lang))
        return "", None, "text"
    await message.reply(t("voice_listening", lang))
    try:
        buffer = await bot.download(voice.file_id)
    except Exception:
        buffer = None
    if buffer is None:
        await message.reply(t("voice_empty", lang))
        return "", None, "text"
    transcript = await stt.transcribe(
        buffer.read(), filename="voice.ogg", mime=voice.mime_type or "audio/ogg"
    )
    if not transcript:
        await message.reply(t("voice_empty", lang))
        return "", voice.file_id, "voice"
    await message.answer(
        t("voice_saved", lang, text=notifier.esc(truncate(transcript, 800)))
    )
    return transcript, voice.file_id, "voice"


async def _queue_check(
    submission,
    homework,
    lang: str,
    text: str,
    images: list[tuple[bytes, str]],
    reply_to: int | None,
    message: Message,
) -> None:
    """Hand the submission to the background AI worker and confirm receipt."""
    worker = get_worker()
    queued_ahead = worker.queue_size
    accepted = worker.submit(
        CheckJob(
            homework_id=homework.id,
            submission_id=submission.id,
            chat_id=homework.chat_id,
            student_id=submission.student_id,
            lang=lang,
            attempts=submission.attempts or 1,
            text=text,
            images=images,
            reply_to=reply_to,
        )
    )
    if not accepted:
        await message.reply(t("st_submit_queue_full", lang))
        return
    if queued_ahead:
        await message.reply(t("st_submit_queued", lang, count=queued_ahead))
    else:
        await message.reply(t("st_submit_saved", lang))


class SubmissionFilter(BaseFilter):
    """True when a group message looks like a student handing in homework."""

    async def __call__(self, message: Message) -> bool:
        if message.text and message.text.startswith("/"):
            return False
        if message.photo or message.document or message.voice:
            return True
        text = (message.text or message.caption or "").strip()
        return len(text) >= 8 and len(text.split()) >= 2



async def process_submission(
    bot: Bot,
    session,
    message: Message,
    homework,
    lang: str,
    student,
) -> None:
    """Save the work and hand it to the background AI worker (app/ai_worker.py)."""
    text = (message.text or message.caption or "").strip()
    images = await _collect_images(bot, message)
    file_id = None
    media_type = "text"
    if message.photo:
        file_id, media_type = message.photo[-1].file_id, "photo"
    elif message.document:
        file_id, media_type = message.document.file_id, "document"
    elif message.voice is not None:
        transcript, voice_id, voice_kind = await _voice_to_text(bot, message, lang)
        if transcript:
            text = stt.combine(text, transcript)
            file_id, media_type = voice_id, voice_kind
        elif not text and not images:
            return     # the "please write" reply was already sent

    if not text and not images:
        await message.reply(t("fb_no_text", lang))
        return

    submission = await submission_service.upsert(
        session, homework, student.tg_id, text, file_id, media_type, message.message_id
    )

    # In confirmation mode the work is parked until the student presses ✅
    # (submitter can still re-send — the parked row is simply updated).
    if settings.confirm_submissions:
        await submission_service.mark_awaiting(session, submission)
        await message.reply(t("sub_confirm_ask", lang, id=submission.id),
                            reply_markup=submission_confirm_kb(submission.id, lang))
        return

    # The AI call runs in the background worker: this handler must return fast
    # so its DB session closes immediately (see app/ai_worker.py).
    await _queue_check(submission, homework, lang, text, images,
                       message.message_id, message)


@router.message(Command("submit", "topshir"))
async def cmd_submit(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    session,
    lang: str,
    is_class: bool,
) -> None:
    if not is_class:
        await message.reply(t("only_group", lang))
        return
    items = await homework_service.active(session, message.chat.id)
    if not items:
        await message.reply(t("st_nothing_due", lang))
        return
    ids = ", ".join(f"#{hw.id}" for hw in items)
    raw = (command.args or "").strip().lstrip("#")
    if raw.isdigit():
        target = next((hw for hw in items if hw.id == int(raw)), None)
    elif len(items) == 1:
        target = items[0]
    else:
        target = None
    if target is None:
        lines = [t("st_submit_which", lang, ids=ids), ""]
        for hw in items:
            lines.append(f"#{hw.id} {notifier.esc(hw.title)} — ⏰ {fmt_datetime(hw.due_at)}")
        await message.reply("\n".join(lines))
        return
    await state.set_state(StudentSubmit.content)
    await state.update_data(homework_id=target.id)
    await message.reply(
        f"#{target.id} {notifier.esc(target.title)}\n" + t("st_submit_usage", lang)
    )


@router.message(StudentSubmit.content)
async def submit_flow(
    message: Message, state: FSMContext, session, lang: str, bot: Bot, is_class: bool
) -> None:
    if not is_class:
        return
    student = await student_service.get_user(session, message.chat.id, message.from_user.id)
    homework = await _resolve_homework(session, message, state)
    await state.clear()
    if homework is None:
        await message.reply(t("st_nothing_due", lang))
        return
    if student is None:
        return
    await process_submission(bot, session, message, homework, lang, student)


@router.message(SubmissionFilter())
async def auto_submission(
    message: Message,
    state: FSMContext,
    session,
    lang: str,
    bot: Bot,
    is_teacher: bool,
    is_class: bool,
) -> None:
    """A student sent text/photo in the group → check it against the homework."""
    if not is_class or is_teacher:
        return
    user = message.from_user
    if user is None or user.is_bot:
        return
    homework = await _resolve_homework(session, message, state)
    if homework is None:
        return  # no active assignment: stay silent
    student = await student_service.get_user(session, message.chat.id, user.id)
    if student is None:
        student = await student_service.touch_user(
            session, user.id, message.chat.id, user.full_name, user.username
        )
    await process_submission(bot, session, message, homework, lang, student)


async def _target_chat_id(session, message: Message, is_class: bool) -> int | None:
    """Group id in a group; otherwise the first class the user belongs to."""
    if is_class:
        return message.chat.id
    chats = await student_service.find_class_chats(session, message.from_user.id)
    return chats[0].id if chats else None


async def _my_homework_text(session, chat_id: int, user_id: int, lang: str) -> str:
    items = await homework_service.active(session, chat_id)
    if not items:
        return t("st_nothing_due", lang)
    lines = [t("st_my_homework", lang), ""]
    for homework in items:
        submission = await submission_service.get(session, homework.id, user_id)
        if submission is None:
            status = t("st_status_todo", lang)
        elif submission.is_late:
            status = t("st_status_late", lang)
        else:
            status = t("st_status_done", lang)
        lines.append(
            t("st_hw_line", lang, id=homework.id, title=notifier.esc(homework.title),
              due=fmt_datetime(homework.due_at), status=status)
        )
        if homework.description:
            lines.append(f"   <i>{notifier.esc(homework.description[:200])}</i>")
    return "\n".join(lines)


async def _my_points_text(session, chat_id: int, user_id: int, lang: str) -> str:
    total = await scoring.total(session, chat_id, user_id)
    events = await scoring.recent(session, chat_id, user_id, 10)
    lines = [t("st_my_points", lang, points=total), ""]
    if events:
        lines.append(t("st_points_breakdown", lang))
        for event in events:
            lines.append(
                t("st_points_event", lang, date=fmt_date_short(event.created_at),
                  sign="+" if event.points >= 0 else "-", points=abs(event.points),
                  reason=notifier.esc(event.reason))
            )
    return "\n".join(lines)


async def _my_attendance_text(session, chat_id: int, user_id: int, lang: str) -> str:
    rows = await attendance_service.for_student(session, chat_id, user_id)
    counts = attendance_service.summarise(rows)
    pct = round(counts["attended"] * 100 / counts["total"]) if counts["total"] else 0
    return "\n".join([
        t("st_my_attendance", lang),
        t("st_att_line", lang, present=counts["present"], late=counts["late"],
          absent=counts["absent"], excused=counts["excused"], total=counts["total"]),
        t("rep_attendance_line", lang, present=counts["attended"], total=counts["total"],
          pct=pct),
    ])


async def _my_stats_text(session, chat_id: int, user, lang: str) -> str:
    stats = await reports_service.collect(session, chat_id, user, "weekly")
    return reports_service.render_student(stats, lang, "weekly")


@router.message(Command("myhomework", "vazifalarim"))
async def cmd_my_homework(message: Message, session, lang: str, is_class: bool) -> None:
    chat_id = await _target_chat_id(session, message, is_class)
    if chat_id is None:
        await message.reply(t("st_no_class", lang))
        return
    await message.answer(await _my_homework_text(session, chat_id, message.from_user.id, lang))


@router.message(Command("mypoints", "ballarim"))
async def cmd_my_points(message: Message, session, lang: str, is_class: bool) -> None:
    chat_id = await _target_chat_id(session, message, is_class)
    if chat_id is None:
        await message.reply(t("st_no_class", lang))
        return
    await message.answer(await _my_points_text(session, chat_id, message.from_user.id, lang))


@router.message(Command("myattendance", "davomatim"))
async def cmd_my_attendance(message: Message, session, lang: str, is_class: bool) -> None:
    chat_id = await _target_chat_id(session, message, is_class)
    if chat_id is None:
        await message.reply(t("st_no_class", lang))
        return
    await message.answer(
        await _my_attendance_text(session, chat_id, message.from_user.id, lang)
    )


@router.message(Command("mystats", "natijalarim"))
async def cmd_my_stats(message: Message, session, lang: str, is_class: bool) -> None:
    chat_id = await _target_chat_id(session, message, is_class)
    if chat_id is None:
        await message.reply(t("st_no_class", lang))
        return
    user = await student_service.get_user(session, chat_id, message.from_user.id)
    if user is None:
        await message.reply(t("st_no_class", lang))
        return
    await message.answer(await _my_stats_text(session, chat_id, user, lang))


@router.message(Command("mytasks", "topshiriqlarim"))
async def cmd_my_tasks(message: Message, session, lang: str, is_class: bool) -> None:
    chat_id = await _target_chat_id(session, message, is_class)
    if chat_id is None:
        await message.reply(t("st_no_class", lang))
        return
    tasks = await scoring.extra_tasks(session, chat_id, message.from_user.id)
    if not tasks:
        await message.reply(t("pen_extra_none", lang))
        return
    lines = [t("pen_extra_list", lang), ""]
    for task in tasks:
        lines.append(f"• {fmt_date_short(task.created_at)} — {notifier.esc(task.reason)}")
    await message.answer("\n".join(lines))


@router.callback_query(F.data.startswith("me:"))
async def me_callback(callback: CallbackQuery, session, lang: str) -> None:
    action = callback.data.split(":")[1]
    user_id = callback.from_user.id
    chats = await student_service.find_class_chats(session, user_id)
    if not chats:
        await callback.answer(t("st_no_class", lang), show_alert=True)
        return
    chat_id = chats[0].id
    if action == "homework":
        text = await _my_homework_text(session, chat_id, user_id, lang)
    elif action == "points":
        text = await _my_points_text(session, chat_id, user_id, lang)
    elif action == "attendance":
        text = await _my_attendance_text(session, chat_id, user_id, lang)
    elif action == "stats":
        user = await student_service.get_user(session, chat_id, user_id)
        text = (
            await _my_stats_text(session, chat_id, user, lang)
            if user is not None
            else t("st_no_class", lang)
        )
    else:
        text = t("unknown", lang)
    await callback.message.answer(text)
    await callback.answer()


@router.callback_query(F.data.startswith("sub:yes:") | F.data.startswith("sub:no:"))
async def submission_callback(callback: CallbackQuery, session, lang: str) -> None:
    """The student confirms (or discards) their own parked submission."""
    _, action, submission_id = (callback.data or "").split(":")[:3]
    try:
        row = await submission_service.get_by_id(session, int(submission_id))
    except (TypeError, ValueError):
        row = None
    if row is None or not submission_service.is_awaiting(row):
        await callback.answer(t("sub_confirm_missing", lang), show_alert=True)
        return
    if row.student_id != callback.from_user.id:
        await callback.answer(t("sub_confirm_denied", lang), show_alert=True)
        return
    if action == "yes":
        await submission_service.confirm(session, row)
        homework = await homework_service.get(session, row.homework_id, row.chat_id)
        if homework is None:
            await callback.answer(t("sub_confirm_missing", lang), show_alert=True)
            return
        images: list[tuple[bytes, str]] = []
        if row.media_type == "photo":
            try:
                buffer = await callback.bot.download(row.media_file_id)
                if buffer is not None:
                    images = [(buffer.read(), "image/jpeg")]
            except Exception:
                images = []
        await _queue_check(row, homework, lang, row.content or "", images,
                           row.message_id, callback.message)
        await callback.message.answer(t("sub_confirm_ok", lang))
    elif action == "no":
        await submission_service.cancel(session, row)
        await callback.message.answer(t("sub_confirm_cancelled", lang))
    else:
        await callback.answer(t("unknown", lang))
        return
    await callback.answer()

