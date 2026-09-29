"""Time, text and parsing helpers (all datetimes are naive local time)."""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta

from .config import settings

_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_WEEKDAYS_SHORT = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


def now() -> datetime:
    """Current local time (naive, in the configured timezone)."""
    return datetime.now(settings.tz).replace(tzinfo=None)


def today() -> date:
    return now().date()


def tzinfo():
    return settings.tz


def combine(day: date, hhmm: str) -> datetime:
    """Combine a date with an 'HH:MM' string."""
    parsed = parse_time(hhmm) or time(0, 0)
    return datetime.combine(day, parsed)


def parse_time(value: str) -> time | None:
    match = re.fullmatch(r"\s*(\d{1,2})[:.\- ]?(\d{2})\s*", value or "")
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return time(hour, minute)


def fmt_date(value: date | datetime | None) -> str:
    if value is None:
        return "—"
    day = value.date() if isinstance(value, datetime) else value
    return f"{day.day} {_MONTHS[day.month - 1]} {day.year}"


def fmt_date_short(value: date | datetime | None) -> str:
    if value is None:
        return "—"
    day = value.date() if isinstance(value, datetime) else value
    return f"{day.day:02d}.{day.month:02d}.{day.year}"


def fmt_datetime(value: datetime | None) -> str:
    if value is None:
        return "—"
    return f"{fmt_date_short(value)}, {value.strftime('%H:%M')}"


def fmt_time(value: time | None) -> str:
    return value.strftime("%H:%M") if value else "—"


def fmt_weekday(index: int) -> str:
    return _WEEKDAYS[index % 7]


def fmt_weekday_short(index: int) -> str:
    return _WEEKDAYS_SHORT[index % 7]


def relative(value: datetime | None) -> str:
    """Human friendly 'in 3 hours' / '2 hours ago'."""
    if value is None:
        return "—"
    seconds = int((value - now()).total_seconds())
    past = seconds < 0
    seconds = abs(seconds)
    if seconds < 60:
        unit, amount = "second", seconds
    elif seconds < 3600:
        unit, amount = "minute", seconds // 60
    elif seconds < 86400:
        unit, amount = "hour", seconds // 3600
    else:
        unit, amount = "day", seconds // 86400
    plural = "" if amount == 1 else "s"
    return f"{amount} {unit}{plural} {'ago' if past else 'left'}"


def truncate(text: str, limit: int = 900) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def first_name(full_name: str) -> str:
    parts = (full_name or "").strip().split()
    return parts[0] if parts else "Student"


def parse_due(text: str, base: datetime | None = None) -> datetime | None:
    """
    Parse a human deadline such as:
        'tomorrow 14:00' | 'today 18:30' | 'friday' | 'next monday 09:00'
        '25.12 10:00' | '25.12.2026' | 'in 3 hours' | 'in 2 days' | '14:00'
    """
    raw = (text or "").strip().lower()
    if not raw:
        return None
    base = base or now()

    match = re.fullmatch(r"(?:in\s+)?(\d+)\s*(min|minute|hour|day|week|daqiqa|soat|kun|hafta)s?", raw)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        delta = {
            "min": timedelta(minutes=amount),
            "minute": timedelta(minutes=amount),
            "daqiqa": timedelta(minutes=amount),
            "hour": timedelta(hours=amount),
            "soat": timedelta(hours=amount),
            "day": timedelta(days=amount),
            "kun": timedelta(days=amount),
            "week": timedelta(weeks=amount),
            "hafta": timedelta(weeks=amount),
        }[unit]
        return base + delta

    day, hhmm = None, None
    if " " in raw:
        date_part, _, time_part = raw.partition(" ")
        hhmm = parse_time(time_part)
        day = _parse_date_part(date_part, base)
    else:
        hhmm = parse_time(raw)
        if hhmm is None:
            day = _parse_date_part(raw, base)

    if day is None:
        return None
    return datetime.combine(day, hhmm or time(23, 59))


def _parse_date_part(part: str, base: datetime) -> date | None:
    part = part.strip()
    if part in {"today", "bugun", "hozir"}:
        return base.date()
    if part in {"tomorrow", "ertaga", "ertaingi"}:
        return (base + timedelta(days=1)).date()
    if part == "day after tomorrow":
        return (base + timedelta(days=2)).date()
    if part.startswith("next ") or part.startswith("keyingi"):
        return _next_weekday(base, part.split(" ", 1)[1])
    return _parse_date_part_raw(part, base)


def _parse_date_part_raw(part: str, base: datetime) -> date | None:
    for name in _WEEKDAYS:
        if part in {name.lower(), name[:3].lower()}:
            return _next_weekday(base, part)
    for name in _MONTHS:
        if part in {name.lower(), name[:3].lower()}:
            return _next_month_day(base, _MONTHS.index(name) + 1)
    for sep in (".", "/", "-"):
        if sep in part:
            chunks = [c for c in part.split(sep) if c]
            if len(chunks) == 2 and all(c.isdigit() for c in chunks):
                return _resolve_day_month(base, int(chunks[0]), int(chunks[1]), None)
            if len(chunks) == 3 and all(c.isdigit() for c in chunks):
                day, month, year = (int(c) for c in chunks)
                return _resolve_day_month(base, day, month, year)
    if part.isdigit() and len(part) == 4:
        return _resolve_day_month(base, base.day, base.month, int(part))
    return None


def _next_weekday(base: datetime, name: str) -> date | None:
    key = name.strip().lower()[:3]
    for index, short in enumerate(_WEEKDAYS_SHORT):
        if short.lower().startswith(key) or _WEEKDAYS[index].lower().startswith(key):
            ahead = (index - base.weekday()) % 7
            return (base + timedelta(days=ahead or 7)).date()
    return None


def _next_month_day(base: datetime, month: int) -> date:
    for year in (base.year, base.year + 1):
        try:
            return date(year, month, base.day)
        except ValueError:
            continue
    return base.date()


def _resolve_day_month(base: datetime, day: int, month: int, year: int | None) -> date | None:
    target_year = year or base.year
    if year is None and (day, month) < (base.day, base.month):
        target_year += 1
    try:
        return date(target_year, month, day)
    except ValueError:
        return None


def next_lesson_after(weekdays: dict[int, time], base: datetime | None = None) -> datetime | None:
    """Given a weekly timetable {weekday: start_time}, return the next lesson start."""
    base = base or now()
    if not weekdays:
        return None
    for offset in range(0, 15):
        day = base + timedelta(days=offset)
        lesson_time = weekdays.get(day.weekday())
        if lesson_time is None:
            continue
        moment = datetime.combine(day.date(), lesson_time)
        if moment > base:
            return moment
    return None
