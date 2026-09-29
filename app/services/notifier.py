"""Rendering + sending of every bot message (shared by handlers and scheduler)."""

from __future__ import annotations

from html import escape
from typing import Any, Sequence

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..i18n import (
    category_label,
    grade_for,
    level_label,
    skill_label,
    t,
    task_status_label,
    verdict_label,
)
from ..keyboards import feedback_review_kb
from ..models import Homework, Submission, User
from ..utils import fmt_datetime, relative

MAX_LEN = 3800


def esc(value: Any) -> str:
    return escape(str(value if value is not None else ""), quote=False)


def chunks(text: str, limit: int = MAX_LEN) -> list[str]:
    """Split a long message on line boundaries (Telegram limit is 4096)."""
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    current: list[str] = []
    size = 0
    for line in text.split("\n"):
        while len(line) > limit:
            head, line = line[:limit], line[limit:]
            parts.append("\n".join(current + [head]))
            current, size = [], 0
        if size + len(line) + 1 > limit:
            parts.append("\n".join(current))
            current, size = [], 0
        current.append(line)
        size += len(line) + 1
    if current:
        parts.append("\n".join(current))
    return parts


async def send_long(
    bot: Bot, chat_id: int, text: str, thread_id: int | None = None, **kwargs: Any
) -> None:
    """Send text, splitting it and falling back to plain text if HTML breaks.

    ``thread_id`` keeps the message inside the right forum topic.
    """
    extra: dict[str, Any] = {}
    if thread_id:
        extra["message_thread_id"] = thread_id
    for index, part in enumerate(chunks(text)):
        try:
            await bot.send_message(
                chat_id, part, **(kwargs if index == 0 else {}), **extra
            )
        except TelegramBadRequest:
            plain = (
                part.replace("<b>", "").replace("</b>", "")
                .replace("<i>", "").replace("</i>", "")
                .replace("<code>", "").replace("</code>", "")
            )
            await bot.send_message(chat_id, plain, **extra)


def render_homework(homework: Homework, lang: str) -> str:
    """The assignment announcement posted in the group."""
    lines = [t("hw_new", lang, id=homework.id), f"📚 <b>{esc(homework.title)}</b>"]
    if homework.skill:
        lines.append(f"🎯 {esc(skill_label(homework.skill, lang))}")
    if homework.description:
        lines.append("")
        lines.append(esc(homework.description))
    if homework.criteria:
        lines.append("")
        lines.append(f"📏 <i>{esc(homework.criteria)}</i>")
    lines.append("")
    lines.append(
        f"⏰ Deadline: <b>{fmt_datetime(homework.due_at)}</b> ({relative(homework.due_at)})"
    )
    lines.append(t("st_submit_usage", lang))
    return "\n".join(lines)


def render_feedback(
    submission: Submission,
    homework: Homework | None,
    student: User,
    points: float,
    lang: str,
) -> str:
    """Student-facing analysis of one checked homework."""
    lines = [
        t("fb_title", lang, id=submission.id),
        t("fb_student", lang, name=esc(student.full_name)),
    ]
    if submission.status in {"checked", "manual"}:
        lines.append(t("fb_score", lang, score=submission.ai_score,
                       grade=submission.ai_grade or grade_for(submission.ai_score)))
        lines.append(t("fb_verdict", lang, verdict=verdict_label(submission.ai_verdict, lang)))
    if submission.is_late:
        lines.append(t("fb_late", lang))
    if points:
        lines.append(t("fb_points", lang, points=points))

    if submission.ai_summary:
        lines.append("")
        lines.append(t("fb_summary", lang))
        lines.append(esc(submission.ai_summary))

    if submission.ai_tasks:
        lines.append("")
        lines.append(t("fb_tasks", lang))
        for item in submission.ai_tasks[:20]:
            task = esc(item.get("task") or item.get("name") or "—")
            status = task_status_label(str(item.get("status") or ""), lang)
            comment = esc(item.get("comment") or item.get("note") or "")
            lines.append(
                f"• <b>{task}</b> — {status}" + (f"\n   <i>{comment}</i>" if comment else "")
            )

    if submission.ai_mistakes:
        lines.append("")
        lines.append(t("fb_mistakes", lang))
        for index, mistake in enumerate(submission.ai_mistakes[:12], start=1):
            original = esc(mistake.get("original") or "—")
            correction = esc(mistake.get("correction") or "—")
            category = category_label(str(mistake.get("category") or "other"), lang)
            rule = esc(mistake.get("rule") or "")
            explanation = esc(mistake.get("explanation") or "")
            lines.append(f"<b>{index}. {t('fb_you_sent', lang, original=original)}</b>")
            lines.append(f"   ✅ {t('fb_correct_is', lang, correction=correction)}")
            lines.append(
                f"   🏷 {category}" + (f" · {t('fb_rule', lang, rule=rule)}" if rule else "")
            )
            if explanation:
                lines.append(f"   💬 {explanation}")
            lines.append("")
    else:
        lines.append("")
        lines.append(t("fb_no_mistakes", lang))

    if submission.ai_strengths:
        lines.append("")
        lines.append(t("fb_strengths", lang))
        lines.extend(f"• {esc(item)}" for item in submission.ai_strengths[:5])

    if submission.ai_tips:
        lines.append("")
        lines.append(t("fb_tips", lang))
        lines.extend(f"• {esc(item)}" for item in submission.ai_tips[:5])

    if submission.ai_topics:
        lines.append("")
        lines.append(t("fb_topics", lang))
        for topic in submission.ai_topics[:6]:
            name = esc(topic.get("topic") or topic.get("name") or "—")
            level = level_label(str(topic.get("level") or "ok"), lang)
            note = esc(topic.get("note") or topic.get("comment") or "")
            lines.append(f"• <b>{name}</b> — {level}" + (f" · {note}" if note else ""))

    if submission.ai_level:
        lines.append("")
        lines.append(t("fb_level", lang, level=esc(submission.ai_level)))
    if submission.teacher_comment:
        lines.append(t("fb_teacher_note", lang, comment=esc(submission.teacher_comment)))
    return "\n".join(lines)


async def publish_homework(
    bot: Bot, homework: Homework, lang: str, thread_id: int | None = None
) -> int | None:
    """Post the assignment to the group and return the message id.

    ``thread_id`` pins it into the Homework topic (falls back to General when
    the topic was deleted or the group is not a forum).
    """
    text = render_homework(homework, lang)
    caption = text if len(text) <= 1024 else text[:1020]
    kwargs: dict = {}
    if thread_id:
        kwargs["message_thread_id"] = thread_id
    try:
        if homework.media_file_id and homework.media_type == "photo":
            message = await bot.send_photo(homework.chat_id, homework.media_file_id,
                                           caption=caption, **kwargs)
        elif homework.media_file_id:
            message = await bot.send_document(homework.chat_id, homework.media_file_id,
                                              caption=caption, **kwargs)
        else:
            message = await bot.send_message(homework.chat_id, text, **kwargs)
        if len(text) > 1024:
            await send_long(bot, homework.chat_id, text, thread_id=thread_id)
        return message.message_id
    except TelegramBadRequest:
        try:  # topic deleted → retry in General
            if homework.media_file_id and homework.media_type == "photo":
                message = await bot.send_photo(
                    homework.chat_id, homework.media_file_id, caption=caption
                )
            elif homework.media_file_id:
                message = await bot.send_document(
                    homework.chat_id, homework.media_file_id, caption=caption
                )
            else:
                message = await bot.send_message(homework.chat_id, text)
            if len(text) > 1024:
                await send_long(bot, homework.chat_id, text)
            return message.message_id
        except Exception:
            await send_long(bot, homework.chat_id, text)
            return None


async def send_feedback(
    bot: Bot,
    submission: Submission,
    homework: Homework | None,
    student: User,
    points: float,
    lang: str,
    reply_to: int | None = None,
) -> None:
    text = render_feedback(submission, homework, student, points, lang)
    markup = feedback_review_kb(submission.id, lang)
    try:
        if reply_to:
            await bot.send_message(submission.chat_id, text, reply_to_message_id=reply_to,
                                   reply_markup=markup)
        else:
            await send_long(bot, submission.chat_id, text, reply_markup=markup)
    except TelegramBadRequest:
        await send_long(bot, submission.chat_id, text)


async def send_reminder(bot: Bot, homework: Homework, hours: int, lang: str) -> None:
    text = (
        f"🔔 <b>Reminder</b> — {t('fb_title', lang, id=homework.id)}\n"
        f"{esc(homework.title)}\n"
        f"⏰ {fmt_datetime(homework.due_at)} ({hours}h left)"
    )
    try:
        await bot.send_message(homework.chat_id, text)
    except TelegramBadRequest:
        pass


async def send_missing_report(
    bot: Bot, homework: Homework, outcome: Sequence[dict], lang: str
) -> None:
    """After a deadline: name the students who did not submit, and escalate."""
    thread_id = getattr(homework, "thread_id", None)
    lines = [
        t("pen_missing_title", lang, id=homework.id, title=esc(homework.title)),
        f"⏰ {fmt_datetime(homework.due_at)}",
        "",
    ]
    for entry in outcome:
        lines.append(t("pen_missing_line", lang, name=esc(entry["student"].full_name),
                       points=entry["points"]))
    await send_long(bot, homework.chat_id, "\n".join(lines), thread_id=thread_id)

    for entry in outcome:
        name = esc(entry["student"].full_name)
        if entry.get("warning"):
            await send_long(bot, homework.chat_id,
                            t("pen_warning", lang, name=name, count=entry["miss_count"]),
                            thread_id=thread_id)
        if entry.get("extra_task"):
            await send_long(
                bot, homework.chat_id,
                t("pen_extra_assigned", lang, name=name, hours=48,
                  task=esc(entry["extra_task"])),
                thread_id=thread_id,
            )


async def send_question(
    bot: Bot,
    chat_id: int,
    question,           # models.TestQuestion
    index: int,
    total: int,
    test_id: int,
    lang: str,
    thread_id: int | None = None,
) -> int | None:
    """Post one quiz question with A/B/C/D buttons into the Test topic."""
    options = list(question.options or [])
    builder = InlineKeyboardBuilder()
    letters = ("A", "B", "C", "D")
    for position, option in enumerate(options[:4]):
        builder.button(
            text=f"{letters[position]}) {option[:40]}",
            callback_data=f"test:{test_id}:{question.id}:{position}",
        )
    builder.adjust(1)
    text = t("test_question", lang, position=index, total=total,
             text=esc(question.text))
    try:
        message = await bot.send_message(
            chat_id, text, reply_markup=builder.as_markup(),
            message_thread_id=thread_id or None,
        )
        return message.message_id
    except TelegramBadRequest:
        try:
            message = await bot.send_message(chat_id, text, reply_markup=builder.as_markup())
            return message.message_id
        except Exception:
            return None
