"""Attendance tracking."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Attendance
from ..utils import now

STATUSES = ("present", "late", "absent", "excused")
CYCLE = {"present": "absent", "absent": "late", "late": "excused", "excused": "present"}


async def set_status(
    session: AsyncSession,
    chat_id: int,
    student_id: int,
    day: date,
    status: str,
    marked_by: int = 0,
) -> Attendance:
    if status not in STATUSES:
        status = "present"
    result = await session.execute(
        select(Attendance).where(
            Attendance.chat_id == chat_id,
            Attendance.student_id == student_id,
            Attendance.day == day,
        )
    )
    row = result.scalars().first()
    if row is None:
        row = Attendance(
            chat_id=chat_id,
            student_id=student_id,
            day=day,
            status=status,
            marked_by=marked_by,
            marked_at=now(),
        )
        session.add(row)
    else:
        row.status = status
        row.marked_by = marked_by
        row.marked_at = now()
    await session.flush()
    return row


async def for_day(session: AsyncSession, chat_id: int, day: date) -> dict[int, Attendance]:
    result = await session.execute(
        select(Attendance).where(Attendance.chat_id == chat_id, Attendance.day == day)
    )
    return {int(row.student_id): row for row in result.scalars().all()}


async def for_student(
    session: AsyncSession,
    chat_id: int,
    student_id: int,
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> list[Attendance]:
    stmt = select(Attendance).where(
        Attendance.chat_id == chat_id, Attendance.student_id == student_id
    )
    if start is not None:
        stmt = stmt.where(Attendance.day >= start)
    if end is not None:
        stmt = stmt.where(Attendance.day <= end)
    result = await session.execute(stmt.order_by(Attendance.day))
    return list(result.scalars().all())


def summarise(rows: list[Attendance]) -> dict[str, int]:
    counts = {status: 0 for status in STATUSES}
    for row in rows:
        counts[row.status if row.status in counts else "present"] += 1
    counts["total"] = len(rows)
    counts["attended"] = counts["present"] + counts["late"]
    return counts


async def stats(
    session: AsyncSession,
    chat_id: int,
    student_id: int,
    start: date,
    end: date,
) -> dict[str, int]:
    rows = await for_student(session, chat_id, student_id, start, end)
    return summarise(rows)


async def group_stats(
    session: AsyncSession, chat_id: int, start: date, end: date
) -> dict[int, dict[str, int]]:
    result = await session.execute(
        select(Attendance).where(
            Attendance.chat_id == chat_id,
            Attendance.day >= start,
            Attendance.day <= end,
        )
    )
    grouped: dict[int, list[Attendance]] = {}
    for row in result.scalars().all():
        grouped.setdefault(int(row.student_id), []).append(row)
    return {sid: summarise(rows) for sid, rows in grouped.items()}


async def lesson_days(session: AsyncSession, chat_id: int, start: date, end: date) -> list[date]:
    result = await session.execute(
        select(Attendance.day)
        .where(Attendance.chat_id == chat_id, Attendance.day >= start, Attendance.day <= end)
        .group_by(Attendance.day)
        .order_by(Attendance.day)
    )
    return [row[0] for row in result.all()]


async def count_marked(session: AsyncSession, chat_id: int, start: date, end: date) -> int:
    result = await session.execute(
        select(func.count(func.distinct(Attendance.day))).where(
            Attendance.chat_id == chat_id,
            Attendance.day >= start,
            Attendance.day <= end,
        )
    )
    return int(result.scalar() or 0)


def points_for_status(status: str) -> float:
    from ..config import settings

    rules = settings.points
    return {
        "present": 0.0,
        "late": rules.attendance_late,
        "absent": rules.absent,
        "excused": 0.0,
    }.get(status, 0.0)
