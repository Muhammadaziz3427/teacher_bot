"""Middleware: one DB session + language + role per update."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import ChatMemberUpdated, TelegramObject

from .config import settings
from .db import session_scope
from .i18n import DEFAULT_LANG
from .services import students as student_service


class AppContextMiddleware(BaseMiddleware):
    """
    Opens a transactional DB session, registers the chat/user, resolves the
    group language and the teacher flag, then injects everything into `data`.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        tg_chat = data.get("event_chat")

        # ChatMemberUpdated carries no sender (event_from_user) when the
        # membership change is about a *different* person (a member joining /
        # leaving). Such updates only get a session; handlers resolve people
        # from the update itself.
        if isinstance(event, ChatMemberUpdated):
            newcomer = getattr(event.new_chat_member, "user", None)
            if tg_user is None and newcomer is None:
                async with session_scope() as session:
                    data["session"] = session
                    data["lang"] = DEFAULT_LANG
                    data["chat_row"] = (
                        await student_service.get_chat(session, tg_chat.id, tg_chat.title)
                        if tg_chat is not None and tg_chat.type in {"group", "supergroup"}
                        else None
                    )
                    data["is_teacher"] = False
                    data["is_class"] = (
                        tg_chat is not None and tg_chat.type in {"group", "supergroup"}
                    )
                    return await handler(event, data)

        async with session_scope() as session:
            data["session"] = session
            lang = DEFAULT_LANG
            is_teacher = False
            chat_row = None

            if tg_user is not None:
                is_teacher = settings.is_teacher(tg_user.id) or settings.is_admin(tg_user.id)

            chat_id = tg_chat.id if tg_chat is not None else (tg_user.id if tg_user else 0)
            is_class = tg_chat is not None and tg_chat.type in {"group", "supergroup"}

            if is_class:
                chat_row = await student_service.get_chat(session, tg_chat.id, tg_chat.title)
                lang = chat_row.language or DEFAULT_LANG
                # A message carrying a thread id proves this is a forum group.
                thread_id = getattr(event, "message_thread_id", None)
                if thread_id and not chat_row.is_forum:
                    chat_row.is_forum = True
                    await session.flush()
                if tg_user is not None:
                    account = await student_service.touch_user(
                        session,
                        tg_user.id,
                        tg_chat.id,
                        tg_user.full_name,
                        tg_user.username,
                        is_teacher,
                    )
                    is_teacher = is_teacher or account.role in {"teacher", "admin"}
            elif tg_user is not None:
                # private chat: keep a lightweight record so /mystats works
                account = await student_service.touch_user(
                    session,
                    tg_user.id,
                    chat_id,
                    tg_user.full_name,
                    tg_user.username,
                    is_teacher,
                )
                is_teacher = is_teacher or account.role in {"teacher", "admin"}

            data["lang"] = lang
            data["chat_row"] = chat_row
            data["is_teacher"] = is_teacher
            data["is_class"] = is_class

            if isinstance(event, ChatMemberUpdated) and data.get("event_chat") is not None:
                chat_row = await student_service.get_chat(
                    session, data["event_chat"].id, data["event_chat"].title
                )
                data["chat_row"] = chat_row
                if chat_row.language:
                    data["lang"] = chat_row.language

            return await handler(event, data)
