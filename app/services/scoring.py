"""Points, penalties, streaks and the escalation ladder."""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..ai_checker import CheckResult
from ..config import settings
from ..models import Homework, PointEvent, Submission, User
from ..utils import now

KIND_HW_DONE = "homework_done"
KIND_HW_PARTIAL = "homework_partial"
KIND_HW_WRONG = "homework_wrong"
KIND_HW_LATE = "homework_late"
KIND_HW_MISSING = "homework_missing"
KIND_ATT_ABSENT = "attendance_absent"
KIND_ATT_LATE = "attendance_late"
KIND_BONUS = "bonus"
KIND_PENALTY = "penalty"
KIND_STREAK = "streak_bonus"
KIND_EXTRA = "extra_task"

STREAK_LENGTH = 3
STREAK_BONUS = 1.0
EXTRA_TASK_HOURS = 48


def points_for(score: int, verdict: str, is_late: bool) -> tuple[float, str]:
    """Turn an AI verdict into (points, kind)."""
    rules = settings.points
    if verdict == "correct" or score >= 80:
        base, kind = rules.full, KIND_HW_DONE
    elif verdict == "partial" or score >= 50:
        base, kind = rules.partial, KIND_HW_PARTIAL
    else:
        base, kind = rules.wrong, KIND_HW_WRONG

    total = base
    if is_late:
        if rules.late_halves_score:
            total = base / 2
        penalty = rules.late
        total += penalty
        kind = KIND_HW_LATE
    return round(total, 2), kind


async def award(
    session: AsyncSession,
    chat_id: int,
    student_id: int,
    kind: str,
    points: float,
    reason: str = "",
    homework_id: Optional[int] = None,
    created_by: int = 0,
    event_key: Optional[str] = None,
) -> PointEvent:
    """Add a ledger entry. With `event_key` it is idempotent (updates instead)."""
    if event_key:
        result = await session.execute(
            select(PointEvent).where(PointEvent.event_key == event_key)
        )
        existing = result.scalars().first()
        if existing is not None:
            existing.points = round(float(points), 2)
            existing.reason = reason or existing.reason
            existing.kind = kind
            await session.flush()
            return existing

    event = PointEvent(
        chat_id=chat_id,
        student_id=student_id,
        kind=kind,
        points=round(float(points), 2),
        reason=(reason or "")[:400],
        homework_id=homework_id,
        event_key=event_key,
        created_by=created_by,
        created_at=now(),
    )
    session.add(event)
    await session.flush()
    return event


async def total(
    session: AsyncSession,
    chat_id: int,
    student_id: int,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> float:
    stmt = select(func.coalesce(func.sum(PointEvent.points), 0.0)).where(
        PointEvent.chat_id == chat_id, PointEvent.student_id == student_id
    )
    if start is not None:
        stmt = stmt.where(PointEvent.created_at >= start)
    if end is not None:
        stmt = stmt.where(PointEvent.created_at <= end)
    result = await session.execute(stmt)
    return round(float(result.scalar() or 0.0), 2)


async def totals_map(
    session: AsyncSession, chat_id: int, start: datetime, end: datetime
) -> dict[int, float]:
    result = await session.execute(
        select(PointEvent.student_id, func.coalesce(func.sum(PointEvent.points), 0.0))
        .where(
            PointEvent.chat_id == chat_id,
            PointEvent.created_at >= start,
            PointEvent.created_at <= end,
        )
        .group_by(PointEvent.student_id)
    )
    return {int(row[0]): round(float(row[1] or 0.0), 2) for row in result.all()}


async def recent(
    session: AsyncSession, chat_id: int, student_id: int, limit: int = 10
) -> list[PointEvent]:
    result = await session.execute(
        select(PointEvent)
        .where(PointEvent.chat_id == chat_id, PointEvent.student_id == student_id)
        .order_by(PointEvent.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def events_kind_between(
    session: AsyncSession,
    chat_id: int,
    kind: str,
    start: datetime,
    end: datetime,
    student_id: Optional[int] = None,
) -> list[PointEvent]:
    stmt = select(PointEvent).where(
        PointEvent.chat_id == chat_id,
        PointEvent.kind == kind,
        PointEvent.created_at >= start,
        PointEvent.created_at <= end,
    )
    if student_id is not None:
        stmt = stmt.where(PointEvent.student_id == student_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def missing_count(session: AsyncSession, chat_id: int, student_id: int) -> int:
    result = await session.execute(
        select(func.count()).select_from(PointEvent).where(
            PointEvent.chat_id == chat_id,
            PointEvent.student_id == student_id,
            PointEvent.kind == KIND_HW_MISSING,
        )
    )
    return int(result.scalar() or 0)


async def award_for_submission(
    session: AsyncSession,
    submission: Submission,
    homework: Homework,
    result: CheckResult,
    chat_id: int,
    student_id: int,
) -> float:
    """Convert a checked submission into points (idempotent per submission)."""
    from . import submissions as submissions_service

    points, kind = points_for(result.score, result.verdict, submission.is_late)
    reason = f"Homework #{homework.id} — {homework.title or homework.topic}"
    await award(
        session,
        chat_id,
        student_id,
        kind,
        points,
        reason,
        homework_id=homework.id,
        event_key=f"sub:{submission.id}",
    )
    await submissions_service.set_points(session, submission, points)
    bonus = await maybe_streak(session, chat_id, student_id)
    return round(points + bonus, 2)


async def maybe_streak(session: AsyncSession, chat_id: int, student_id: int) -> float:
    """Reward {STREAK_LENGTH} on-time submissions in a row (once per submission)."""
    from . import submissions as submissions_service

    rows = await submissions_service.for_student(session, chat_id, student_id)
    recent = rows[-STREAK_LENGTH:]
    if len(recent) < STREAK_LENGTH or any(row.is_late for row in recent):
        return 0.0
    trigger = recent[-1]
    await award(
        session,
        chat_id,
        student_id,
        KIND_STREAK,
        STREAK_BONUS,
        f"{STREAK_LENGTH} homeworks on time in a row",
        homework_id=trigger.homework_id,
        event_key=f"streak:{chat_id}:{student_id}:{trigger.id}",
    )
    return STREAK_BONUS


async def apply_missing(
    session: AsyncSession,
    homework: Homework,
    students: Sequence[User],
    lang: str = "bi",
) -> list[dict]:
    """
    Penalise every student who did not submit in time and escalate:
    first miss → warning, second and later → an AI-generated extra task.
    """
    from ..ai_checker import suggest_extra_task

    rules = settings.points
    outcome: list[dict] = []
    for student in students:
        count = await missing_count(session, homework.chat_id, student.tg_id) + 1
        await award(
            session,
            homework.chat_id,
            student.tg_id,
            KIND_HW_MISSING,
            rules.missing,
            f"Homework #{homework.id} not submitted — {homework.title or homework.topic}",
            homework_id=homework.id,
            event_key=f"hw-missing:{homework.id}:{student.tg_id}",
        )
        entry = {
            "student": student,
            "points": rules.missing,
            "miss_count": count,
            "warning": count == 1,
            "extra_task": None,
        }
        if count >= 2:
            task = await suggest_extra_task(homework, (), lang)
            await award(
                session,
                homework.chat_id,
                student.tg_id,
                KIND_EXTRA,
                0.0,
                task,
                homework_id=homework.id,
                event_key=f"extra:{homework.id}:{student.tg_id}",
            )
            entry["extra_task"] = task
        outcome.append(entry)
    return outcome


async def assign_extra(
    session: AsyncSession,
    chat_id: int,
    student_id: int,
    task: str,
    created_by: int = 0,
) -> PointEvent:
    return await award(
        session, chat_id, student_id, KIND_EXTRA, 0.0, task, created_by=created_by
    )


async def extra_tasks(
    session: AsyncSession, chat_id: int, student_id: int, limit: int = 10
) -> list[PointEvent]:
    result = await session.execute(
        select(PointEvent)
        .where(
            PointEvent.chat_id == chat_id,
            PointEvent.student_id == student_id,
            PointEvent.kind == KIND_EXTRA,
        )
        .order_by(PointEvent.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def manual(
    session: AsyncSession,
    chat_id: int,
    student_id: int,
    points: float,
    reason: str,
    created_by: int = 0,
) -> PointEvent:
    kind = KIND_BONUS if points >= 0 else KIND_PENALTY
    return await award(
        session, chat_id, student_id, kind, points, reason, created_by=created_by
    )


async def attendance_points(
    session: AsyncSession, chat_id: int, student_id: int, status: str, day: str
) -> float:
    """Award/deduct points for a day's attendance (idempotent per day)."""
    from .attendance import points_for_status

    points = points_for_status(status)
    if points == 0:
        return 0.0
    kind = KIND_ATT_ABSENT if status == "absent" else KIND_ATT_LATE
    await award(
        session,
        chat_id,
        student_id,
        kind,
        points,
        f"Attendance ({day}) — {status}",
        event_key=f"att:{chat_id}:{student_id}:{day}",
    )
    return points
