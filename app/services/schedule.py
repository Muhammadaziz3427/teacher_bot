"""Weekly timetable and the 'next lesson' deadline logic."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import LessonSlot
from ..utils import fmt_time, fmt_weekday, next_lesson_after, now, parse_time


async def list_slots(session: AsyncSession, chat_id: int) -> list[LessonSlot]:
    result = await session.execute(
        select(LessonSlot)
        .where(LessonSlot.chat_id == chat_id, LessonSlot.enabled.is_(True))
        .order_by(LessonSlot.weekday, LessonSlot.start_time)
    )
    return list(result.scalars().all())


async def add_slot(
    session: AsyncSession, chat_id: int, weekday: int, start_time: str, subject: str = ""
) -> LessonSlot | None:
    parsed = parse_time(start_time)
    if parsed is None:
        return None
    normalised = parsed.strftime("%H:%M")
    existing = await session.execute(
        select(LessonSlot).where(
            LessonSlot.chat_id == chat_id,
            LessonSlot.weekday == weekday,
            LessonSlot.start_time == normalised,
        )
    )
    slot = existing.scalars().first()
    if slot is not None:
        slot.enabled = True
        await session.flush()
        return slot
    slot = LessonSlot(
        chat_id=chat_id,
        weekday=weekday,
        start_time=normalised,
        subject=subject or settings.subject,
    )
    session.add(slot)
    await session.flush()
    return slot


async def remove_slot(session: AsyncSession, chat_id: int, slot_id: int) -> bool:
    slot = await session.get(LessonSlot, slot_id)
    if slot is None or slot.chat_id != chat_id:
        return False
    await session.delete(slot)
    await session.flush()
    return True


async def clear_slots(session: AsyncSession, chat_id: int) -> int:
    slots = await list_slots(session, chat_id)
    for slot in slots:
        await session.delete(slot)
    await session.flush()
    return len(slots)


async def timetable_map(session: AsyncSession, chat_id: int) -> dict[int, object]:
    """{weekday: time} of the first lesson of each day."""
    mapping: dict[int, object] = {}
    for slot in await list_slots(session, chat_id):
        parsed = parse_time(slot.start_time)
        if parsed is None:
            continue
        current = mapping.get(slot.weekday)
        if current is None or parsed < current:
            mapping[slot.weekday] = parsed
    return mapping


async def next_lesson(session: AsyncSession, chat_id: int, base: datetime | None = None) -> datetime | None:
    return next_lesson_after(await timetable_map(session, chat_id), base or now())


async def next_lesson_or_none(session: AsyncSession, chat_id: int) -> datetime | None:
    return await next_lesson(session, chat_id)


async def default_due(session: AsyncSession, chat_id: int, base: datetime | None = None) -> datetime:
    """Deadline = start of the next lesson, or now + DEFAULT_DUE_HOURS."""
    base = base or now()
    moment = await next_lesson(session, chat_id, base)
    if moment is None:
        return base + timedelta(hours=settings.default_due_hours)
    return moment


async def timetable_text(session: AsyncSession, chat_id: int, lang: str = "bi") -> str:
    slots = await list_slots(session, chat_id)
    if not slots:
        from ..i18n import t

        return t("tt_empty", lang)
    lines = []
    for slot in slots:
        lines.append(
            f"#{slot.id} · {fmt_weekday(slot.weekday)} — {fmt_time(parse_time(slot.start_time))}"
        )
    return "\n".join(lines)


def describe_due(moment: datetime | None) -> str:
    if moment is None:
        return "—"
    return f"{fmt_weekday(moment.weekday())}, {moment.strftime('%d.%m.%Y %H:%M')}"
