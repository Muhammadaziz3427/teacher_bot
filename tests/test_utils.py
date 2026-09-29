"""Pure time/text helpers — no DB, no network."""
from __future__ import annotations

from datetime import datetime, time, timedelta

from app.utils import (
    first_name,
    fmt_weekday,
    next_lesson_after,
    now,
    parse_due,
    parse_time,
    relative,
    truncate,
)

BASE = datetime(2026, 9, 28, 10, 0)   # a Monday


def test_parse_time_accepts_common_separators():
    assert parse_time("14:00") == time(14, 0)
    assert parse_time("14.30") == time(14, 30)
    assert parse_time(" 9-05 ") == time(9, 5)


def test_parse_time_rejects_impossible_values():
    assert parse_time("25:00") is None
    assert parse_time("14:99") is None
    assert parse_time("nonsense") is None


def test_parse_due_relative():
    assert parse_due("in 3 hours", BASE) == BASE + timedelta(hours=3)
    assert parse_due("in 2 days", BASE) == BASE + timedelta(days=2)


def test_parse_due_tomorrow_evening():
    parsed = parse_due("tomorrow 18:00", BASE)
    assert parsed == datetime(2026, 9, 29, 18, 0)


def test_parse_due_nonsense_is_rejected():
    assert parse_due("whenever you like", BASE) is None


def test_next_lesson_from_timetable():
    # BASE is Monday 10:00, the lesson is Monday 14:00
    assert next_lesson_after({0: time(14, 0)}, BASE) == datetime(2026, 9, 28, 14, 0)


def test_next_lesson_wraps_to_next_week():
    # Monday 14:00 already passed → the same lesson next Monday
    later = datetime(2026, 9, 28, 15, 0)
    assert next_lesson_after({0: time(14, 0)}, later) == datetime(2026, 10, 5, 14, 0)


def test_next_lesson_without_timetable():
    assert next_lesson_after({}, BASE) is None


def test_fmt_weekday_is_monday_first():
    assert fmt_weekday(0) == "Monday"
    assert fmt_weekday(6) == "Sunday"


def test_relative_counts_down_and_back():
    # relative() always compares against the real clock, so use now() here
    base = now()
    ahead = relative(base + timedelta(hours=3))
    behind = relative(base - timedelta(hours=2))
    assert ahead.endswith("left") and "hour" in ahead
    assert behind.endswith("ago") and "hour" in behind


def test_truncate_keeps_the_limit():
    cut = truncate("x" * 1000, 100)
    assert len(cut) <= 100 and cut.endswith("…")
    assert truncate("short", 100) == "short"


def test_first_name():
    assert first_name("Aziza Karimova") == "Aziza"
    assert first_name("") == "Student"