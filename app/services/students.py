"""Class roster: chats, users, roles and lookups.

One Telegram account can be a member of many class groups; every membership is
a separate ``User`` row keyed by ``(chat_id, tg_id)``. The numeric ``id`` of a
row is meaningless outside its own group — always look people up by
``(chat_id, tg_id)``.
"""

from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import Chat, GroupTeacher, User


async def get_chat(session: AsyncSession, chat_id: int, title: str | None = None) -> Chat:
    chat = await session.get(Chat, chat_id)
    if chat is None:
        chat = Chat(id=chat_id, title=title or "", subject=settings.subject,
                    default_due_hours=settings.default_due_hours, language="bi")
        session.add(chat)
        await session.flush()
    elif title and chat.title != title:
        chat.title = title
    return chat


async def set_language(session: AsyncSession, chat_id: int, lang: str) -> Chat:
    chat = await get_chat(session, chat_id)
    chat.language = lang
    await session.flush()
    return chat


async def touch_user(
    session: AsyncSession,
    user_id: int,
    chat_id: int,
    full_name: str,
    username: str | None = None,
    is_teacher: bool = False,
) -> User:
    """Create or refresh ONE GROUP's membership row (multi-group safe)."""
    result = await session.execute(
        select(User).where(User.chat_id == chat_id, User.tg_id == user_id)
    )
    user = result.scalars().first()
    if user is None:
        user = User(
            tg_id=user_id,
            chat_id=chat_id,
            full_name=full_name or f"Student {user_id}",
            username=username,
            role="teacher" if is_teacher else "student",
        )
        session.add(user)
    else:
        if full_name:
            user.full_name = full_name
        if username:
            user.username = username
        if is_teacher and user.role == "student":
            user.role = "teacher"
    await session.flush()
    return user


async def get_user(session: AsyncSession, chat_id: int, user_id: int) -> User | None:
    result = await session.execute(
        select(User).where(User.chat_id == chat_id, User.tg_id == user_id)
    )
    return result.scalars().first()


async def list_students(session: AsyncSession, chat_id: int) -> list[User]:
    result = await session.execute(
        select(User)
        .where(User.chat_id == chat_id, User.role == "student", User.is_active.is_(True))
        .order_by(User.full_name)
    )
    return list(result.scalars().all())


async def all_users(session: AsyncSession, chat_id: int) -> list[User]:
    result = await session.execute(
        select(User).where(User.chat_id == chat_id).order_by(User.role, User.full_name)
    )
    return list(result.scalars().all())


async def count_students(session: AsyncSession, chat_id: int) -> int:
    result = await session.execute(
        select(func.count()).select_from(User).where(
            User.chat_id == chat_id, User.role == "student", User.is_active.is_(True)
        )
    )
    return int(result.scalar() or 0)


async def find_student(session: AsyncSession, chat_id: int, query: str) -> User | None:
    """Find a student by numeric id, @username or (partial) full name."""
    raw = (query or "").strip()
    if not raw:
        return None

    if raw.lstrip("-").isdigit():
        user = await get_user(session, chat_id, int(raw))
        if user is not None:
            return user

    students = await list_students(session, chat_id)
    if raw.startswith("@"):
        needle = raw[1:].lower()
        for student in students:
            if (student.username or "").lower() == needle:
                return student
        return None

    needle = raw.lower()
    for student in students:  # exact first
        if student.full_name.lower() == needle:
            return student
    for student in students:  # then partial
        if needle in student.full_name.lower() or needle in (student.username or "").lower():
            return student
    return None


async def set_role(session: AsyncSession, chat_id: int, user_id: int, role: str) -> User | None:
    user = await get_user(session, chat_id, user_id)
    if user is None:
        return None
    user.role = role
    await session.flush()
    return user


async def set_active(session: AsyncSession, chat_id: int, user_id: int, active: bool) -> User | None:
    user = await get_user(session, chat_id, user_id)
    if user is None:
        return None
    user.is_active = active
    await session.flush()
    return user


async def find_class_chats(session: AsyncSession, user_id: int) -> list[Chat]:
    """All class groups this Telegram user belongs to (for private-chat stats)."""
    result = await session.execute(
        select(Chat).join(User, User.chat_id == Chat.id).where(User.tg_id == user_id)
    )
    return list(result.scalars().all())


def display_name(user: User | None) -> str:
    if user is None:
        return "—"
    return user.full_name or (f"@{user.username}" if user.username else str(user.tg_id))


# --------------------------------------------------------------------------
# Teacher ↔ group assignments (learning center: several groups, several staff)
# --------------------------------------------------------------------------
async def teacher_chats(session: AsyncSession, tg_id: int) -> list[Chat]:
    """Every group the person may open in the private dashboard.

    A person sees a group when they are a global admin, listed in the
    ``TEACHER_IDS`` config, registered inside the group as teacher/admin, or
    explicitly assigned through :func:`assign_teacher` (and their assignment
    has not been revoked — revoking is done with :func:`unassign_teacher`).
    """
    direct = await session.execute(
        select(Chat).join(User, User.chat_id == Chat.id).where(
            User.tg_id == tg_id, User.is_active.is_(True), User.role.in_(("teacher", "admin"))
        )
    )
    chats: dict[int, Chat] = {row.id: row for row in direct.scalars().all()}
    if settings.is_teacher(tg_id) or settings.is_admin(tg_id):
        rows = (await session.execute(select(Chat))).scalars().all()
        chats.update({row.id: row for row in rows})
    else:
        assigned = await session.execute(
            select(Chat).join(GroupTeacher, GroupTeacher.chat_id == Chat.id).where(
                GroupTeacher.tg_id == tg_id
            )
        )
        chats.update({row.id: row for row in assigned.scalars().all()})
    return sorted(chats.values(), key=lambda row: row.title or "")


async def can_open_group(session: AsyncSession, tg_id: int, chat_id: int) -> bool:
    if settings.is_admin(tg_id) or settings.is_teacher(tg_id):
        return True
    direct = await session.execute(
        select(User).where(User.chat_id == chat_id, User.tg_id == tg_id,
                           User.is_active.is_(True), User.role.in_(("teacher", "admin")))
    )
    if direct.scalars().first() is not None:
        return True
    assigned = await session.execute(
        select(GroupTeacher).where(GroupTeacher.chat_id == chat_id, GroupTeacher.tg_id == tg_id)
    )
    return assigned.scalars().first() is not None


async def assign_teacher(
    session: AsyncSession, chat_id: int, tg_id: int, assigned_by: int = 0
) -> GroupTeacher:
    result = await session.execute(
        select(GroupTeacher).where(
            GroupTeacher.chat_id == chat_id, GroupTeacher.tg_id == tg_id
        )
    )
    row = result.scalars().first()
    if row is None:
        row = GroupTeacher(chat_id=chat_id, tg_id=tg_id, assigned_by=assigned_by)
        session.add(row)
        await session.flush()
    return row


async def unassign_teacher(session: AsyncSession, chat_id: int, tg_id: int) -> bool:
    result = await session.execute(
        select(GroupTeacher).where(
            GroupTeacher.chat_id == chat_id, GroupTeacher.tg_id == tg_id
        )
    )
    row = result.scalars().first()
    if row is None:
        return False
    await session.delete(row)
    await session.flush()
    return True


async def group_managers(session: AsyncSession, chat_id: int) -> list[GroupTeacher]:
    result = await session.execute(
        select(GroupTeacher).where(GroupTeacher.chat_id == chat_id)
    )
    return list(result.scalars().all())
