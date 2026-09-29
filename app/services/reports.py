"""Weekly / monthly / yearly reports for students and the whole class."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..i18n import cefr_for, category_label, period_label, t
from ..models import Homework, Submission, User
from ..utils import fmt_date_short, now
from . import attendance as attendance_service
from . import homework as homework_service
from . import scoring
from . import students as student_service
from . import submissions as submission_service

PERIODS = ("weekly", "monthly", "yearly")


def period_bounds(period: str, ref: date | None = None) -> tuple[date, date]:
    ref = ref or now().date()
    if period == "monthly":
        return ref.replace(day=1), ref
    if period == "yearly":
        return ref.replace(month=1, day=1), ref
    return ref - timedelta(days=6), ref


def previous_bounds(period: str, ref: date | None = None) -> tuple[date, date]:
    start, end = period_bounds(period, ref)
    span = (end - start).days + 1
    new_end = start - timedelta(days=1)
    return new_end - timedelta(days=span - 1), new_end


def as_datetimes(start: date, end: date) -> tuple[datetime, datetime]:
    return datetime.combine(start, time.min), datetime.combine(end, time.max)


@dataclass(slots=True)
class StudentStats:
    """Everything a report needs about one student for one period."""

    student: User
    start: date
    end: date
    assigned: int = 0
    submitted: int = 0
    ontime: int = 0
    late: int = 0
    missing: int = 0
    avg: float = 0.0
    scores: list[int] = field(default_factory=list)
    points: float = 0.0
    rank: int = 0
    class_size: int = 0
    attendance: dict[str, int] = field(default_factory=dict)
    categories: dict[str, int] = field(default_factory=dict)
    rules: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    examples: list[dict] = field(default_factory=list)
    level: str = ""
    trend: float = 0.0

    @property
    def attendance_pct(self) -> int:
        total = self.attendance.get("total", 0)
        if total <= 0:
            return 0
        return round(self.attendance.get("attended", 0) * 100 / total)

    @property
    def completion_pct(self) -> int:
        if self.assigned <= 0:
            return 100 if self.submitted else 0
        return round(self.submitted * 100 / self.assigned)


async def _rank_of(
    session: AsyncSession, chat_id: int, student_id: int, start: date, end: date
) -> tuple[int, int]:
    """Return (place, class size) by points earned in the period."""
    start_dt, end_dt = as_datetimes(start, end)
    totals = await scoring.totals_map(session, chat_id, start_dt, end_dt)
    students = await student_service.list_students(session, chat_id)
    ids = [s.tg_id for s in students]
    ordered = sorted(
        (totals.get(sid, 0.0) for sid in ids), reverse=True
    )
    mine = totals.get(student_id, 0.0)
    try:
        place = ordered.index(mine) + 1
    except ValueError:
        place = len(ids) or 1
    return place, len(ids)


async def collect(
    session: AsyncSession,
    chat_id: int,
    student: User,
    period: str = "weekly",
    with_history: bool = True,
) -> StudentStats:
    """Gather all numbers for one student in the given period."""
    start, end = period_bounds(period)
    start_dt, end_dt = as_datetimes(start, end)

    homeworks = await homework_service.homeworks_between(session, chat_id, start_dt, end_dt)
    subs = await submission_service.for_student(session, chat_id, student.tg_id, start_dt, end_dt)
    by_homework: dict[int, Submission] = {s.homework_id: s for s in subs}

    stats = StudentStats(student=student, start=start, end=end)
    stats.assigned = len(homeworks)
    graded: list[int] = []
    for homework in homeworks:
        submission = by_homework.get(homework.id)
        if submission is None:
            stats.missing += 1
            continue
        stats.submitted += 1
        if submission.is_late:
            stats.late += 1
        else:
            stats.ontime += 1
        if submission.status in {"checked", "manual"}:
            graded.append(submission.ai_score)

    stats.scores = graded
    stats.avg = round(sum(graded) / len(graded), 1) if graded else 0.0
    stats.points = await scoring.total(session, chat_id, student.tg_id, start_dt, end_dt)
    stats.attendance = await attendance_service.stats(session, chat_id, student.tg_id, start, end)
    stats.categories = submission_service.mistake_categories(subs)
    stats.rules = submission_service.mistake_rules(subs)
    stats.strengths = submission_service.strengths(subs)
    stats.examples = pick_examples(subs)
    stats.level = cefr_for(int(stats.avg), student.level or "")
    stats.rank, stats.class_size = await _rank_of(session, chat_id, student.tg_id, start, end)

    if with_history:
        prev_start, prev_end = previous_bounds(period)
        prev_dt_start, prev_dt_end = as_datetimes(prev_start, prev_end)
        prev_rows = await submission_service.for_student(
            session, chat_id, student.tg_id, prev_dt_start, prev_dt_end
        )
        prev_scores = [r.ai_score for r in prev_rows if r.status in {"checked", "manual"}]
        if prev_scores:
            stats.trend = round(stats.avg - (sum(prev_scores) / len(prev_scores)), 1)
    return stats


def pick_examples(rows: Sequence[Submission], limit: int = 4) -> list[dict]:
    """Collect distinct example mistakes (original → correction) for reports."""
    seen: set[str] = set()
    examples: list[dict] = []
    for row in rows:
        for mistake in row.ai_mistakes or []:
            if not isinstance(mistake, dict):
                continue
            original = str(mistake.get("original") or "").strip()
            correction = str(mistake.get("correction") or "").strip()
            if not (original and correction):
                continue
            key = f"{original.lower()}->{correction.lower()}"
            if key in seen:
                continue
            seen.add(key)
            examples.append({
                "original": original,
                "correction": correction,
                "category": mistake.get("category") or "other",
                "rule": mistake.get("rule") or "",
            })
            if len(examples) >= limit:
                return examples
    return examples


def _errors_block(stats: StudentStats, lang: str, limit: int = 5) -> list[str]:
    if not stats.categories:
        return [t("fb_no_mistakes", lang)]
    lines = [t("rep_errors", lang)]
    for category, count in list(stats.categories.items())[:limit]:
        lines.append(
            t("rep_errors_line", lang, category=category_label(category, lang), count=count)
        )
    return lines


def _focus_block(stats: StudentStats, lang: str) -> list[str]:
    lines = [t("rep_focus", lang)]
    if stats.rules:
        lines.append(t("rep_focus_rules", lang, rules="; ".join(stats.rules)))
    elif stats.categories:
        names = [category_label(c, lang) for c, _ in list(stats.categories.items())[:2]]
        lines.append(t("rep_focus_rules", lang, rules=", ".join(names)))
    else:
        lines.append(t("rep_focus_rules", lang, rules=stats.student.level or "the lesson topic"))
    return lines


def parent_note(stats: StudentStats, lang: str) -> str:
    name = (stats.student.full_name or "Student").split()[0]
    absent = stats.attendance.get("absent", 0) + stats.attendance.get("late", 0)
    if stats.attendance.get("total", 0) and stats.attendance_pct < 75:
        return t("rep_note_attendance", lang, name=name, absent=absent)
    if stats.missing >= 2:
        return t("rep_note_homework", lang, name=name, missing=stats.missing)
    if stats.avg and stats.avg < 55:
        return t("rep_note_score", lang, avg=stats.avg)
    return t("rep_note_good", lang, name=name)


def render_student(stats: StudentStats, lang: str, period: str = "weekly") -> str:
    """Render one student's report — ready to forward to a parent."""
    lines = [
        t("rep_student_title", lang, period=period_label(period, lang)),
        f"<b>{stats.student.full_name}</b>"
        + (f" — {stats.student.level}" if stats.student.level else ""),
        t("rep_period_line", lang,
          start=fmt_date_short(stats.start), end=fmt_date_short(stats.end)),
        "",
        t("rep_attendance_line", lang,
          present=stats.attendance.get("attended", 0),
          total=stats.attendance.get("total", 0),
          pct=stats.attendance_pct),
        t("rep_hw_line", lang,
          done=stats.submitted, assigned=stats.assigned, ontime=stats.ontime,
          late=stats.late, avg=stats.avg),
    ]
    if stats.missing:
        lines.append(t("rep_missing_line", lang, count=stats.missing,
                       points=round(settings.points.missing * stats.missing, 2)))
    lines.append(t("rep_points_line", lang, points=stats.points))
    if stats.rank and stats.class_size:
        lines.append(t("rep_rank_line", lang, rank=stats.rank, total=stats.class_size))
    if stats.trend > 0:
        lines.append(t("rep_trend_up", lang, value=abs(stats.trend)))
    elif stats.trend < 0:
        lines.append(t("rep_trend_down", lang, value=abs(stats.trend)))
    elif stats.scores:
        lines.append(t("rep_trend_same", lang))
    lines.append("")
    lines.extend(_errors_block(stats, lang))
    if stats.examples:
        lines.append(t("rep_examples", lang))
        for example in stats.examples[:3]:
            lines.append(
                t("rep_example_line", lang, original=example["original"],
                  correction=example["correction"])
            )
    if stats.strengths:
        lines.append("")
        lines.append(t("rep_strengths", lang))
        lines.extend(f"• {item}" for item in stats.strengths)
    if stats.submitted and not stats.categories:
        lines.append(t("rep_no_errors", lang, count=len(stats.scores) or stats.submitted))
    if stats.submitted and stats.late == 0:
        lines.append(t("rep_punctual", lang))
    lines.append("")
    lines.extend(_focus_block(stats, lang))
    lines.append("")
    lines.append(t("rep_parent_note", lang))
    lines.append(parent_note(stats, lang))
    return "\n".join(lines)


async def student_report(
    session: AsyncSession, chat_id: int, student: User, period: str, lang: str
) -> tuple[str, StudentStats]:
    """Return (text, stats) for one student."""
    stats = await collect(session, chat_id, student, period)
    return render_student(stats, lang, period), stats


async def collect_all(
    session: AsyncSession, chat_id: int, period: str
) -> list[StudentStats]:
    students = await student_service.list_students(session, chat_id)
    return [
        await collect(session, chat_id, student, period, with_history=False)
        for student in students
    ]


async def group_report(session: AsyncSession, chat_id: int, period: str, lang: str) -> str:
    """Whole-class report posted in the group / kept for the teacher."""
    stats_list = await collect_all(session, chat_id, period)
    if not stats_list:
        return t("rep_nobody", lang)
    start, end = period_bounds(period)
    lines = [
        t("rep_group_title", lang, period=period_label(period, lang)),
        t("rep_period_line", lang, start=fmt_date_short(start), end=fmt_date_short(end)),
        "",
    ]
    avgs = [s.avg for s in stats_list if s.scores]
    if avgs:
        lines.append(t("rep_class_avg", lang, avg=round(sum(avgs) / len(avgs), 1)))
    for stats in sorted(stats_list, key=lambda s: s.points, reverse=True):
        lines.append("")
        lines.append(f"<b>{stats.student.full_name}</b> — {stats.points} pts")
        lines.append(t("rep_attendance_line", lang,
                       present=stats.attendance.get("attended", 0),
                       total=stats.attendance.get("total", 0), pct=stats.attendance_pct))
        lines.append(t("rep_hw_line", lang, done=stats.submitted, assigned=stats.assigned,
                       ontime=stats.ontime, late=stats.late, avg=stats.avg))
        if stats.missing:
            lines.append(t("rep_missing_line", lang, count=stats.missing,
                           points=round(settings.points.missing * stats.missing, 2)))
    ranked = sorted([s for s in stats_list if s.points], key=lambda s: s.points, reverse=True)
    if ranked:
        lines.append("")
        lines.append(t("rep_top", lang))
        for place, stats in enumerate(ranked[:3], start=1):
            lines.append(t("rank_line", lang, place=place, name=stats.student.full_name,
                           points=stats.points, avg=stats.avg))
    needy = [
        s for s in stats_list
        if s.missing >= 2 or (s.attendance.get("total", 0) and s.attendance_pct < 70)
    ]
    if needy:
        lines.append("")
        lines.append(t("rep_need_help", lang))
        for stats in needy:
            lines.append(
                f"• {stats.student.full_name} — {stats.missing} missing, "
                f"{stats.attendance_pct}% attendance"
            )
    return "\n".join(lines)


async def ranking(session: AsyncSession, chat_id: int, period: str, lang: str) -> str:
    stats_list = await collect_all(session, chat_id, period)
    if not stats_list:
        return t("rep_nobody", lang)
    lines = [t("rank_title", lang, period=period_label(period, lang)), ""]
    ordered = sorted(stats_list, key=lambda s: (s.points, s.avg), reverse=True)
    for place, stats in enumerate(ordered, start=1):
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(place, f"{place}.")
        lines.append(f"{medal} {stats.student.full_name} — {stats.points} pts (avg {stats.avg})")
    return "\n".join(lines)


async def year_summary(
    session: AsyncSession, chat_id: int, student: User, lang: str
) -> str:
    """Compact certificate-style summary used for the yearly report."""
    stats = await collect(session, chat_id, student, "yearly", with_history=False)
    lessons = stats.attendance.get("total", 0)
    hw_pct = stats.completion_pct
    return t(
        "rep_certificate",
        lang,
        lessons=lessons,
        pct=stats.attendance_pct,
        hw=hw_pct,
        avg=stats.avg,
        level=stats.level or cefr_for(int(stats.avg), student.level or ""),
    )

