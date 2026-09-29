"""Telegram deep links — one tap opens a parent's report in the bot.

``https://t.me/<bot>?start=parent_<chat>_<student>``

Telegram only allows ``[A-Za-z0-9_-]`` in the payload, so the (negative)
group id travels without its minus sign and is restored on the way back.
Only teachers who actually manage that group may open the link — the
payload is not a secret and must never be treated as one.
"""

from __future__ import annotations

PREFIX = "parent"


def build_parent_payload(chat_id: int, student_id: int) -> str:
    return f"{PREFIX}_{abs(int(chat_id))}_{abs(int(student_id))}"


def parse_parent_payload(payload: str | None) -> tuple[int, int] | None:
    """Return ``(chat_id, student_id)`` or ``None`` for anything unexpected."""
    raw = (payload or "").strip()
    parts = raw.split("_")
    if len(parts) != 3 or parts[0] != PREFIX:
        return None
    try:
        chat, student = int(parts[1]), int(parts[2])
    except ValueError:
        return None
    if chat <= 0 or student <= 0:
        return None
    return -chat, student


def parent_url(username: str, chat_id: int, student_id: int) -> str:
    """Full t.me link, or an empty string when the bot username is unknown."""
    user = (username or "").strip().lstrip("@")
    if not user:
        return ""
    return f"https://t.me/{user}?start={build_parent_payload(chat_id, student_id)}"