"""Homework assignments."""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Homework, Submission
from ..utils import now


async def create(
    session: AsyncSession,
    chat_id: int,
    title: str,
    description: str = "",
    due_at: Optional[datetime] = None,
    created_by: int = 0,
    skill: str = "",
    criteria: str = "",
    media_file_id: str | None = None,
    media_type: str = "",
    thread_id: int | None = None,
) -> Homework:
    homework = Homework(
        chat_id=chat_id,
        title=title.strip()[:255],
        topic=title.strip()[:255],
        description=(description or "").strip(),
        criteria=(criteria or "").strip(),
        skill=(skill or "").strip()[:64],
        media_file_id=media_file_id,
        media_type=media_type or "",
        thread_id=thread_id,
        assigned_at=now(),
        due_at=due_at or now(),
        status="active",
        created_by=created_by,
        reminders_sent=[],
    )
    session.add(homework)
    await session.flush()
    return homework


async def get(session: AsyncSession, homework_id: int, chat_id: int | None = None) -> Homework | None:
    homework = await session.get(Homework, homework_id)
    if homework is None:
        return None
    if chat_id is not None and homework.chat_id != chat_id:
        return None
    return homework


async def active(session: AsyncSession, chat_id: int) -> list[Homework]:
    result = await session.execute(
        select(Homework)
        .where(Homework.chat_id == chat_id, Homework.status == "active")
        .order_by(Homework.due_at)
    )
    return list(result.scalars().all())


async def latest_active(session: AsyncSession, chat_id: int) -> Homework | None:
    result = await session.execute(
        select(Homework)
        .where(Homework.chat_id == chat_id, Homework.status == "active")
        .order_by(Homework.due_at.desc())
    )
    return result.scalars().first()


async def by_message(session: AsyncSession, chat_id: int, message_id: int) -> Homework | None:
    result = await session.execute(
        select(Homework).where(
            Homework.chat_id == chat_id, Homework.message_id == message_id
        )
    )
    return result.scalars().first()


async def attach_message(session: AsyncSession, homework: Homework, message_id: int) -> None:
    homework.message_id = message_id
    await session.flush()


async def close(session: AsyncSession, homework: Homework) -> Homework:
    homework.status = "closed"
    homework.closed_at = now()
    await session.flush()
    return homework


async def set_due(session: AsyncSession, homework: Homework, due_at: datetime) -> Homework:
    homework.due_at = due_at
    homework.reminders_sent = []
    await session.flush()
    return homework


async def mark_reminded(session: AsyncSession, homework: Homework, hours: int) -> None:
    sent = list(homework.reminders_sent or [])
    if hours not in sent:
        sent.append(hours)
    homework.reminders_sent = sent
    await session.flush()


async def due_soon(session: AsyncSession, moment: datetime) -> list[Homework]:
    """Active homework whose deadline has already passed."""
    result = await session.execute(
        select(Homework).where(Homework.status == "active", Homework.due_at <= moment)
    )
    return list(result.scalars().all())


async def active_all(session: AsyncSession) -> list[Homework]:
    result = await session.execute(select(Homework).where(Homework.status == "active"))
    return list(result.scalars().all())


async def count_active(session: AsyncSession, chat_id: int) -> int:
    result = await session.execute(
        select(func.count()).select_from(Homework).where(
            Homework.chat_id == chat_id, Homework.status == "active"
        )
    )
    return int(result.scalar() or 0)


async def counts_between(
    session: AsyncSession, chat_id: int, start: datetime, end: datetime
) -> int:
    """How many assignments were due inside the period."""
    result = await session.execute(
        select(func.count()).select_from(Homework).where(
            Homework.chat_id == chat_id, Homework.due_at >= start, Homework.due_at <= end
        )
    )
    return int(result.scalar() or 0)


async def homeworks_between(
    session: AsyncSession, chat_id: int, start: datetime, end: datetime
) -> list[Homework]:
    result = await session.execute(
        select(Homework)
        .where(Homework.chat_id == chat_id, Homework.due_at >= start, Homework.due_at <= end)
        .order_by(Homework.due_at)
    )
    return list(result.scalars().all())


def title_of(homework: Homework | None) -> str:
    if homework is None:
        return "—"
    return homework.title or homework.topic or f"Homework #{homework.id}"


async def overview(session: AsyncSession, homework: Homework) -> dict[str, int]:
    """Quick numbers for the teacher: how many submitted / pending."""
    result = await session.execute(
        select(Submission).where(Submission.homework_id == homework.id)
    )
    rows: Sequence[Submission] = list(result.scalars().all())
    return {
        "submitted": len(rows),
        "late": sum(1 for r in rows if r.is_late),
        "pending": sum(1 for r in rows if r.status == "pending"),
    }
