"""Forum (topic-based) group support.

Telegram forum groups split the chat into topics; every message carries
``message_thread_id`` = the topic it belongs to. The teacher never needs to
know those ids: the bot **auto-detects** them.

Auto-detection rules (all automatic, nothing to configure):
* any message with a thread id proves the group is a forum → ``is_forum``
* ``/homework`` used inside a topic  → that topic = **Homework**
* ``/test`` / ``/testschedule`` used inside a topic → that topic = **Test**
* ``/weekly`` / ``/ranking`` used inside a topic  → that topic = **Announcements**
* the first topic a teacher writes any command in → **General** (default)
* a student's reply is always posted back in the topic of their own message
  (Telegram keeps the thread when you reply), so no mapping is needed there.

Only when a topic was never detected does the bot post to General.
"""

from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from ..models import Chat

TOPIC_FIELDS = {
    "general": "topic_general",
    "homework": "topic_homework",
    "test": "topic_test",
    "announcements": "topic_announcements",
    "announcement": "topic_announcements",
}

KIND_LABEL = {
    "general": "General",
    "homework": "Homework",
    "test": "Test",
    "announcements": "Announcements",
}


def thread_for(chat: Chat | None, kind: str) -> int | None:
    """Stored topic for this kind of message, or None → use General."""
    field = TOPIC_FIELDS.get(kind)
    if chat is None or field is None:
        return None
    value = getattr(chat, field, None)
    return int(value) if value else None


async def remember_topic(
    session, chat: Chat, kind: str, thread_id: int | None
) -> bool:
    """Auto-detect: remember which topic this kind of message belongs to."""
    if thread_id is None:
        return False
    field = TOPIC_FIELDS.get(kind)
    if field is None:
        return False
    if getattr(chat, field, None) == int(thread_id):
        return False
    setattr(chat, field, int(thread_id))
    chat.is_forum = True
    await session.flush()
    return True


async def detect_from_message(session, chat: Chat, kind: str, message) -> bool:
    """Learn the topic from the very message a teacher just sent."""
    thread = getattr(message, "message_thread_id", None)
    if thread is None:
        return False
    chat.is_forum = True
    changed = await remember_topic(session, chat, kind, thread)
    if changed and thread_for(chat, "general") is None:
        await remember_topic(session, chat, "general", thread)
    return changed


async def send_topic(
    bot: Bot,
    chat: Chat | None,
    kind: str,
    text: str,
    *,
    reply_to: int | None = None,
    reply_markup=None,
    parse_mode: str | None = "HTML",
) -> bool:
    """Post into the right topic; falls back to General if the topic vanished."""
    chat_id = chat.id
    thread = thread_for(chat, kind)
    kwargs: dict = {"parse_mode": parse_mode}
    if thread:
        kwargs["message_thread_id"] = thread
    if reply_to:
        kwargs["reply_to_message_id"] = reply_to
    if reply_markup is not None:
        kwargs["reply_markup"] = reply_markup
    try:
        await bot.send_message(chat_id, text, **kwargs)
        return True
    except TelegramBadRequest:
        kwargs.pop("message_thread_id", None)  # topic deleted → General
        try:
            await bot.send_message(chat_id, text, **kwargs)
            return True
        except Exception:
            return False


def topics_status(chat: Chat | None) -> list[tuple[str, int | None]]:
    """(kind, thread id) for /topics — shows what has been auto-detected."""
    return [(kind, thread_for(chat, kind)) for kind in
            ("general", "homework", "test", "announcements")]
