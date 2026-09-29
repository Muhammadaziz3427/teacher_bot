"""Offline end-to-end self-test — no Telegram token and no AI key needed.

Run:  python scripts/selftest.py

It exercises the real code paths: lesson schedule → homework → AI verdict →
points/penalties → escalation → attendance → weekly/monthly/yearly reports →
Excel export → message rendering.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Windows consoles (cp1252/cp1254/…) cannot print → ✅ etc. — force UTF-8 so
# the report never crashes mid-run.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Deterministic + isolated: throwaway DB, offline checker forced.
os.environ["DB_FILE"] = "data/selftest.db"
os.environ["AI_ENABLED"] = "false"
os.environ["OPENAI_API_KEY"] = ""
os.environ["ADMIN_IDS"] = "1"
os.environ["TEACHER_IDS"] = "1"
os.environ["AUTO_WEEKLY_REPORT"] = "false"

from app import ai_checker  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import dispose, init_db, session_scope  # noqa: E402
from app.i18n import t  # noqa: E402
from app.services import attendance as attendance_service  # noqa: E402
from app.services import exporter, notifier, scoring  # noqa: E402
from app.services import homework as homework_service  # noqa: E402
from app.services import reports as reports_service  # noqa: E402
from app.services import schedule as schedule_service  # noqa: E402
from app.services import students as student_service  # noqa: E402
from app.services import submissions as submission_service  # noqa: E402
from app.services import tests as test_service  # noqa: E402
from app.services import topics as topic_service  # noqa: E402
from app import ai_worker as ai_worker_module  # noqa: E402
from app.ai_checker import CheckResult  # noqa: E402
from app.ai_worker import CheckJob  # noqa: E402
from app.keyboards import sections_kb  # noqa: E402
from app.scheduler import close_homework_and_penalise  # noqa: E402
from app.utils import next_lesson_after, now, parse_due, today  # noqa: E402

CHAT_ID = -1001234567890
CHAT_TITLE = "English B1 — Test Group"
TEACHER_ID = 1
STUDENTS = ((101, "Aziza Karimova"), (102, "Bobur Yusupov"), (103, "Dilnoza Ergasheva"))
LANGS = ("en", "uz", "bi")
MINI_TOKEN = "selftest-token"

FAILURES: list[str] = []


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _SendOnlyBot:
    """Scheduler only ever *sends* — nothing else is required from the bot."""

    async def send_message(self, *args, **kwargs):
        return SimpleNamespace(message_id=1)

    async def send_photo(self, *args, **kwargs):
        return SimpleNamespace(message_id=1)


def check(label: str, condition: bool, detail: str = "") -> None:
    mark = "PASS" if condition else "FAIL"
    print(f"  [{mark}] {label}" + (f"  — {detail}" if detail else ""))
    if not condition:
        FAILURES.append(label)


AI_SAMPLE = {
    "score": 78,
    "verdict": "partial",
    "summary": "Good attempt. Watch the 3rd person -s and articles.",
    "task_results": [
        {"task": "Ex. 1a", "status": "correct", "comment": "All correct"},
        {"task": "Ex. 1b", "status": "wrong", "comment": "Missing -s"},
    ],
    "mistakes": [
        {"original": "He go to school", "correction": "He goes to school",
         "category": "tense", "rule": "Present Simple: 3rd person -s",
         "explanation": "he/she/it takes verb + s.", "severity": "major"},
        {"original": "an book", "correction": "a book", "category": "articles",
         "rule": "a/an before a consonant sound",
         "explanation": "Use 'a' before a consonant sound.", "severity": "minor"},
    ],
    "topics": [{"topic": "Present Simple", "level": "weak", "note": "Needs practice"}],
    "strengths": ["Good vocabulary range"],
    "tips": ["Write 5 sentences with he/she/it"],
    "estimated_level": "A2",
}


async def fake_ai(homework, student_text, images=(), lang="bi"):
    """Deterministic stand-in for the vision/text AI check."""
    return ai_checker._normalise(AI_SAMPLE)


async def scenario() -> int:
    bot = DummyBot()

    print("\n=== 1. Deadline parsing & timetable math ===")
    parsed = parse_due("tomorrow 18:00")
    check("parse_due: 'tomorrow 18:00'", parsed is not None and parsed.hour == 18)
    check("parse_due: 'friday' yields a future date",
          (parse_due("friday") or now()) > now())
    check("parse_due: 'in 3 hours'", parse_due("in 3 hours") is not None)
    check("parse_due: nonsense is rejected", parse_due("blah blah") is None)
    lesson = next_lesson_after({0: now().time().replace(hour=14, minute=0)}, now())
    check("next_lesson_after returns a future datetime", lesson is not None)

    async with session_scope() as session:
        print("\n=== 2. Class setup ===")
        await student_service.get_chat(session, CHAT_ID, CHAT_TITLE)
        await student_service.set_language(session, CHAT_ID, "bi")
        teacher = await student_service.touch_user(
            session, TEACHER_ID, CHAT_ID, "Laylo Teacher", "laylo", is_teacher=True
        )
        aziza = await student_service.touch_user(
            session, 101, CHAT_ID, "Aziza Karimova", "aziza"
        )
        bobur = await student_service.touch_user(
            session, 102, CHAT_ID, "Bobur Yusupov", "bobur"
        )
        dilnoza = await student_service.touch_user(
            session, 103, CHAT_ID, "Dilnoza Ergasheva", "dilnoza"
        )
        roster = await student_service.list_students(session, CHAT_ID)
        check("3 students registered", len(roster) == 3, f"got {len(roster)}")
        check("teacher is not in the student roster",
              all(s.tg_id != TEACHER_ID for s in roster))
        check("find_student by @username",
              (await student_service.find_student(session, CHAT_ID, "@bobur")).tg_id == 102)
        check("find_student by partial name",
              (await student_service.find_student(session, CHAT_ID, "dilnoza")).tg_id == 103)

        await schedule_service.add_slot(session, CHAT_ID, 0, "14:00")
        await schedule_service.add_slot(session, CHAT_ID, 2, "14:00")
        slots = await schedule_service.list_slots(session, CHAT_ID)
        check("timetable stores 2 weekly lessons", len(slots) == 2)
        upcoming = await schedule_service.next_lesson(session, CHAT_ID)
        check("next lesson derived from timetable",
              upcoming is not None and upcoming > now(), str(upcoming))
        default_due = await schedule_service.default_due(session, CHAT_ID)
        check("default deadline == next lesson start",
              upcoming is not None and abs((default_due - upcoming).total_seconds()) < 1)

        print("\n=== 3. Homework published (deadline = next lesson) ===")
        hw1 = await homework_service.create(
            session, CHAT_ID, "Present Simple — Unit 3",
            description="Workbook p.14, exercises 1a–1d",
            due_at=now() + timedelta(hours=2), created_by=TEACHER_ID,
            skill="grammar", criteria="Correct 3rd person -s and articles",
        )
        message_id = await notifier.publish_homework(bot, hw1, "bi")
        check("assignment posted to the group", message_id is not None)
        await homework_service.attach_message(session, hw1, message_id or 0)
        check("assignment is linked to its group message",
              (await homework_service.by_message(session, CHAT_ID, message_id or 0)) is not None)
        grouped = (await homework_service.active(session, CHAT_ID))[0]
        check("active homework listed for students", grouped.id == hw1.id)
        rendered_hw = notifier.render_homework(hw1, "en")
        check("assignment message contains title + deadline",
              "Present Simple" in rendered_hw and "Deadline" in rendered_hw)

        print("\n=== 4. AI check → points (on time) ===")
        sub1 = await submission_service.upsert(
            session, hw1, aziza.tg_id, "He go to school every day. I read an book.",
            message_id=11,
        )
        check("on-time submission is not flagged late", sub1.is_late is False)
        verdict = await fake_ai(hw1, sub1.content)
        await submission_service.apply_result(session, sub1, verdict)
        points1 = await scoring.award_for_submission(session, sub1, hw1, verdict, CHAT_ID, aziza.tg_id)
        check("partial work earns +1.0 point", points1 == 1.0, f"got {points1}")
        check("score + grade stored", sub1.ai_score == 78 and sub1.ai_grade == "C",
              f"{sub1.ai_score}/{sub1.ai_grade}")
        check("mistakes stored for the report", len(sub1.ai_mistakes) == 2)
        check("status marked as checked", sub1.status == "checked")
        again = await scoring.award_for_submission(session, sub1, hw1, verdict, CHAT_ID, aziza.tg_id)
        total_aziza = await scoring.total(session, CHAT_ID, aziza.tg_id)
        check("re-checking never double counts", total_aziza == 1.0, f"total={total_aziza}")

        print("\n=== 5. Late submission → halved + penalty ===")
        hw2 = await homework_service.create(
            session, CHAT_ID, "Past Simple — Unit 4",
            due_at=now() - timedelta(hours=1), created_by=TEACHER_ID, skill="grammar",
        )
        sub2 = await submission_service.upsert(
            session, hw2, bobur.tg_id, "I goed to the park yesterday.", message_id=12
        )
        check("past-deadline submission flagged late", sub2.is_late is True)
        verdict2 = await fake_ai(hw2, sub2.content)
        await submission_service.apply_result(session, sub2, verdict2)
        points2 = await scoring.award_for_submission(
            session, sub2, hw2, verdict2, CHAT_ID, bobur.tg_id
        )
        check("late work: half points + -1 penalty = -0.5", points2 == -0.5, f"got {points2}")

    return await _after_session(bot, hw1.id, hw2.id, sub1, points1)


# __SELFTEST_PART_2__

class DummyBot:
    """Captures outgoing messages instead of talking to Telegram."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append(text)
        return SimpleNamespace(message_id=len(self.sent))

    async def send_photo(self, chat_id, photo, caption=None, **kwargs):
        self.sent.append(caption or "")
        return SimpleNamespace(message_id=len(self.sent))

    async def send_document(self, chat_id, document, caption=None, **kwargs):
        self.sent.append(caption or "")
        return SimpleNamespace(message_id=len(self.sent))


def _test_migration() -> None:
    """Simulate a pre-upgrade database and check that rows survive migration."""
    import sqlalchemy as sa

    from app.db import _migrate_user_table

    tmp = ROOT / "data" / "migration_test.db"
    tmp.unlink(missing_ok=True)
    tmp.parent.mkdir(parents=True, exist_ok=True)
    engine = sa.create_engine(f"sqlite:///{tmp.as_posix()}")

    with engine.begin() as conn:  # old schema: telegram id WAS the primary key
        conn.execute(sa.text(
            "CREATE TABLE users ("
            "id INTEGER NOT NULL PRIMARY KEY, chat_id INTEGER, full_name VARCHAR(255),"
            "username VARCHAR(64), role VARCHAR(16), level VARCHAR(16),"
            "is_active BOOLEAN, guardian_contact VARCHAR(120), notes TEXT,"
            "created_at DATETIME)"
        ))
        conn.execute(sa.text(
            "INSERT INTO users (id, chat_id, full_name, role, is_active) "
            "VALUES (101, -100, 'Old Student', 'student', 1)"
        ))

    with engine.begin() as conn:
        _migrate_user_table(conn)

    with engine.connect() as conn:
        cols = {row[1] for row in conn.execute(sa.text("PRAGMA table_info(users)"))}
        check("migration adds tg_id column", "tg_id" in cols, str(sorted(cols)))
        row = conn.execute(sa.text("SELECT tg_id, full_name, role FROM users")).fetchone()
        check("migration preserves existing rows",
              row is not None and row[0] == 101 and row[1] == "Old Student"
              and row[2] == "student",
              str(tuple(row) if row else None))
        has_gt = conn.execute(sa.text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='group_teachers'"
        )).fetchone()
        check("migration creates group_teachers table", has_gt is not None)

    with engine.begin() as conn:  # running it a second time must be a no-op
        _migrate_user_table(conn)
    with engine.connect() as conn:
        count = conn.execute(sa.text("SELECT COUNT(*) FROM users")).scalar()
        check("migration is idempotent", count == 1, f"count={count}")

    engine.dispose()
    tmp.unlink(missing_ok=True)


async def _after_session(bot: DummyBot, hw1_id: int, hw2_id: int, sub1, points1) -> int:
    async with session_scope() as session:
        hw1 = await homework_service.get(session, hw1_id)
        hw2 = await homework_service.get(session, hw2_id)

        print("\n=== 6. Deadline passed → missing + escalation ===")
        outcome = await close_homework_and_penalise(bot, session, hw2, "bi")
        missing_ids = {entry["student"].tg_id for entry in outcome}
        check("non-submitters detected after the deadline", 103 in missing_ids, str(missing_ids))
        check("late submitter (Bobur) is NOT penalised", 102 not in missing_ids)
        dil = next(entry for entry in outcome if entry["student"].tg_id == 103)
        check("missing homework = -3 points", dil["points"] == -3.0)
        check("first miss triggers a warning", dil["warning"] is True)
        check("missing report posted to the group",
              any("Dilnoza" in message for message in bot.sent))
        check("homework closed after the deadline",
              (await homework_service.get(session, hw2_id)).status == "closed")

        hw3 = await homework_service.create(
            session, CHAT_ID, "Articles — Unit 5",
            due_at=now() - timedelta(minutes=5), created_by=TEACHER_ID, skill="grammar",
        )
        outcome2 = await close_homework_and_penalise(bot, session, hw3, "bi")
        dil2 = next(entry for entry in outcome2 if entry["student"].tg_id == 103)
        check("second miss escalates to an AI extra task", bool(dil2["extra_task"]),
              (dil2["extra_task"] or "")[:70])
        check("second miss is no longer just a warning", dil2["warning"] is False)
        check("extra task stored for /mytasks",
              len(await scoring.extra_tasks(session, CHAT_ID, 103)) == 1)
        ledger = await scoring.events_kind_between(
            session, CHAT_ID, scoring.KIND_HW_MISSING,
            now() - timedelta(days=1), now() + timedelta(days=1), 103,
        )
        check("one missing-penalty per homework (idempotent)", len(ledger) == 2,
              f"got {len(ledger)}")

        print("\n=== 7. Attendance ===")
        await attendance_service.set_status(session, CHAT_ID, 101, today(), "present", TEACHER_ID)
        await attendance_service.set_status(session, CHAT_ID, 102, today(), "absent", TEACHER_ID)
        absent_points = await scoring.attendance_points(
            session, CHAT_ID, 102, "absent", today().isoformat()
        )
        check("absence deducts -1 point", absent_points == -1.0)
        counts = await attendance_service.stats(session, CHAT_ID, 102, today(), today())
        check("attendance summary counts the day",
              counts["absent"] == 1 and counts["total"] == 1, str(counts))
        await scoring.attendance_points(session, CHAT_ID, 102, "absent", today().isoformat())
        att_ledger = await scoring.events_kind_between(
            session, CHAT_ID, scoring.KIND_ATT_ABSENT,
            now() - timedelta(days=1), now() + timedelta(days=1), 102,
        )
        check("attendance points are idempotent per day", len(att_ledger) == 1)
        days = await attendance_service.lesson_days(
            session, CHAT_ID, today() - timedelta(days=7), today()
        )
        check("lesson days available to reports", len(days) >= 1)

        print("\n=== 8. Reports (weekly / monthly / yearly × en/uz/bi) ===")
        aziza = await student_service.get_user(session, CHAT_ID, 101)
        stats = await reports_service.collect(session, CHAT_ID, aziza, "weekly")
        check("stats: 3 assigned / 1 submitted",
              stats.assigned == 3 and stats.submitted == 1, f"{stats.assigned}/{stats.submitted}")
        check("stats: average score comes from the AI", stats.avg == 78.0, str(stats.avg))
        check("stats: recurring mistake categories",
              stats.categories.get("tense", 0) >= 1, str(stats.categories))
        check("stats: rank + class size", stats.rank >= 1 and stats.class_size == 3,
              f"{stats.rank}/{stats.class_size}")
        check("stats: attendance percentage", 0 <= stats.attendance_pct <= 100)

        for language in LANGS:
            weekly = (await reports_service.student_report(
                session, CHAT_ID, aziza, "weekly", language))[0]
            monthly = (await reports_service.student_report(
                session, CHAT_ID, aziza, "monthly", language))[0]
            yearly = (await reports_service.student_report(
                session, CHAT_ID, aziza, "yearly", language))[0]
            check(f"weekly/monthly/yearly render in '{language}'",
                  "Aziza" in weekly and len(weekly) > 120 and len(monthly) > 120
                  and len(yearly) > 120)

        report = (await reports_service.student_report(
            session, CHAT_ID, aziza, "weekly", "bi"))[0]
        check("report quotes the correction", "He goes to school" in report)
        check("report quotes the grammar rule", "3rd person -s" in report)
        check("report includes a parents' note",
              "Ota-ona" in report or "parents" in report)

        group_text = await reports_service.group_report(session, CHAT_ID, "weekly", "uz")
        check("group report contains every student",
              all(name in group_text for _, name in STUDENTS))
        check("leaderboard rendered",
              "Aziza Karimova" in await reports_service.ranking(
                  session, CHAT_ID, "weekly", "en"))
        certificate = await reports_service.year_summary(session, CHAT_ID, aziza, "bi")
        check("yearly certificate rendered",
              "Davomat" in certificate or "Attendance" in certificate)

        print("\n=== 9. Excel export ===")
        path = await exporter.build_workbook(session, CHAT_ID, "weekly", "bi")
        check("xlsx file written", path.exists() and path.stat().st_size > 3000, str(path))
        from openpyxl import load_workbook

        workbook = load_workbook(path)
        expected = {"Summary", "Attendance", "Homework", "Mistakes", "Points"}
        check("xlsx contains all sheets", expected <= set(workbook.sheetnames),
              str(workbook.sheetnames))
        sheet = workbook["Summary"]
        header = [cell.value for cell in sheet[1]]
        rows = list(sheet.iter_rows(min_row=2, values_only=True))
        check("xlsx header + one row per student",
              "Student" in header and len(rows) == 3, f"{len(rows)} rows")

        print("\n=== 10. Multi-group support (learning center) ===")
        CHAT2 = -1009876543210
        await student_service.get_chat(session, CHAT2, "English A1 — Second Group")
        # The same Telegram person (101) now joins a SECOND group.
        aziza_in_g2 = await student_service.touch_user(
            session, 101, CHAT2, "Aziza Karimova", "aziza"
        )
        check("same Telegram user exists in two groups",
              aziza_in_g2.tg_id == aziza.tg_id and aziza_in_g2.id != aziza.id,
              f"g1.id={aziza.id} g2.id={aziza_in_g2.id}")
        g1_students = await student_service.list_students(session, CHAT_ID)
        g2_students = await student_service.list_students(session, CHAT2)
        check("rosters are separate per group",
              len(g1_students) == 3 and len(g2_students) == 1,
              f"{len(g1_students)} / {len(g2_students)}")
        g1_points = await scoring.total(session, CHAT_ID, 101)
        g2_points = await scoring.total(session, CHAT2, 101)
        check("points do not leak between groups",
              g1_points != 0.0 and g2_points == 0.0,
              f"g1={g1_points} g2={g2_points}")
        await attendance_service.set_status(session, CHAT2, 101, today(), "absent", TEACHER_ID)
        g1_att = await attendance_service.stats(session, CHAT_ID, 101, today(), today())
        g2_att = await attendance_service.stats(session, CHAT2, 101, today(), today())
        check("attendance does not leak between groups",
              g1_att.get("present", 0) == 1 and g2_att.get("absent", 0) == 1,
              f"g1={g1_att} g2={g2_att}")
        chat2_active = await homework_service.count_active(session, CHAT2)
        check("second group starts with no homework", chat2_active == 0)
        check("first group homework untouched", await homework_service.count_active(session, CHAT_ID) >= 1)

        # Teacher access: global admin sees everything, assigned teacher sees one.
        admin_chats = await student_service.teacher_chats(session, TEACHER_ID)
        check("admin/teacher sees every group", len(admin_chats) >= 2,
              str([c.title for c in admin_chats]))
        check("stranger cannot open a group",
              not await student_service.can_open_group(session, 4242, CHAT2))
        await student_service.assign_teacher(session, CHAT2, 4242, TEACHER_ID)
        check("assigned teacher gains access to that group only",
              await student_service.can_open_group(session, 4242, CHAT2))
        assigned_chats = await student_service.teacher_chats(session, 4242)
        check("assigned teacher sees exactly one group",
              [c.id for c in assigned_chats] == [CHAT2],
              str([c.title for c in assigned_chats]))
        check("assigned teacher still blocked from group 1",
              not await student_service.can_open_group(session, 4242, CHAT_ID))
        check("group managers listed",
              len(await student_service.group_managers(session, CHAT2)) == 1)
        await student_service.unassign_teacher(session, CHAT2, 4242)
        check("revoked assignment removes access",
              not await student_service.can_open_group(session, 4242, CHAT2))
        report_g2 = await reports_service.group_report(session, CHAT2, "weekly", "en")
        check("group_report for group 2 is isolated",
              "Aziza" in report_g2 and "Bobur" not in report_g2)

        # Dashboard keyboards must address the right group, not the private chat.
        from app.keyboards import attendance_kb as _att_kb

        board = _att_kb(g2_students, {}, "en", CHAT2)
        flat = [b.callback_data for row in board.inline_keyboard for b in row]
        check("dashboard attendance buttons carry the group id",
              any(str(CHAT2) in data for data in flat), str(flat[:2]))
        sections = sections_kb(CHAT2, "en")
        flat_sections = [b.callback_data for row in sections.inline_keyboard for b in row]
        targets = [d for d in flat_sections if not d.endswith(":0")]  # skip "back to groups"
        check("dashboard section buttons carry the group id",
              bool(targets) and all(str(CHAT2) in d for d in targets), str(targets[:3]))

        print("\n=== 11. Old-schema DB migration ===")
        _test_migration()

        print("\n=== 12. Forum topics (auto-detection) ===")
        port = _free_port()          # claimed here so §19 can rely on it later
        chat_row = await student_service.get_chat(session, CHAT_ID, CHAT_TITLE)
        fake_thread = SimpleNamespace(message_thread_id=777)
        changed = await topic_service.detect_from_message(session, chat_row, "test", fake_thread)
        check("topic auto-detected from the command's thread",
              changed and chat_row.is_forum is True)
        check("test topic remembered", topic_service.thread_for(chat_row, "test") == 777)
        check("general topic defaults to the first detected",
              topic_service.thread_for(chat_row, "general") == 777)
        await topic_service.detect_from_message(
            session, chat_row, "homework", SimpleNamespace(message_thread_id=888)
        )
        check("a second topic is stored separately",
              topic_service.thread_for(chat_row, "homework") == 888
              and topic_service.thread_for(chat_row, "test") == 777)
        check("undetected kinds fall back to General",
              topic_service.thread_for(chat_row, "announcements") is None)
        check("no thread id → nothing is learned", not await topic_service.detect_from_message(
            session, chat_row, "announcements", SimpleNamespace(message_thread_id=None)
        ))

        print("\n=== 13. Tests (syllabus → quiz → grading) ===")
        await homework_service.create(
            session, CHAT_ID, "Present Perfect — Unit 7",
            due_at=now() + timedelta(days=1), created_by=TEACHER_ID,
        )
        taught = await test_service.taught_topics(session, CHAT_ID)
        check("taught lessons become the test syllabus",
              "Present Perfect — Unit 7" in taught, str(taught[:3]))
        quiz = await test_service.create_test(
            session, CHAT_ID, "Quiz #1", lesson_topics="Present Perfect",
            created_by=TEACHER_ID, duration_minutes=15, thread_id=777,
        )
        await test_service.add_question(
            session, quiz.id, "I ___ never been to London.",
            ["have", "has", "had", "having"], 0, "have",
        )
        await test_service.add_question(
            session, quiz.id, "She ___ her homework yet.",
            ["finish", "hasn't finished", "finishing", "finished"], 1, "negative",
        )
        items = await test_service.questions(session, quiz.id)
        check("questions are numbered in order", [q.position for q in items] == [1, 2])
        posted = await test_service.publish_test(bot, session, quiz, chat_row, "en",
                                                 thread_id=777)
        check("test posted into the test topic",
              posted == 2 and quiz.status == "running")
        check("answering window opened", quiz.ends_at is not None)
        check("question buttons were sent to the group",
              any("Question 1/2" in message for message in bot.sent))

        first = items[0]
        _answer, is_new = await test_service.record_answer(session, quiz.id, first.id, 101, 0)
        check("the first answer counts", is_new is True)
        _again, is_new_again = await test_service.record_answer(
            session, quiz.id, first.id, 101, 1
        )
        check("re-answering does not create a second answer", is_new_again is False)
        await test_service.score_question(session, first.id)
        await test_service.record_answer(session, quiz.id, items[1].id, 102, 1)
        await test_service.score_question(session, items[1].id)
        board = dict(await test_service.leaderboard(session, quiz.id))
        check("leaderboard scores each student",
              board.get(101) == 0 and board.get(102) == 1, str(board))
        results = await test_service.finish_test(bot, session, quiz, chat_row, "en")
        check("results posted and test closed",
              quiz.status == "finished" and "Test #" in results)

        chat_row.test_weekday = 2
        chat_row.test_time = "14:00"
        chat_row.test_count = 5
        await session.flush()
        check("weekly auto-test schedule stored",
              chat_row.test_weekday == 2 and chat_row.test_time == "14:00")

        print("\n=== 14. Message rendering + offline fallback ===")
    feedback = notifier.render_feedback(sub1, hw1, aziza, points1, "bi")
    check("student feedback shows the score", "78/100" in feedback)
    check("student feedback lists the correction", "He goes to school" in feedback)
    check("student feedback lists a tip", "Write 5 sentences" in feedback)
    check("long messages are split for Telegram", len(notifier.chunks("x" * 9000)) > 1)

    offline = await ai_checker.check_submission(hw1, "he go to school. i dont know", [], "uz")
    check("offline fallback: not auto-graded", offline.ok is False)
    check("offline fallback: marked pending for the teacher", offline.status == "pending")
    check("offline fallback: heuristics still help the student",
          any(m["category"] in {"punctuation", "capitalisation"} for m in offline.mistakes),
          str([m["category"] for m in offline.mistakes]))

    # --- 15. Background AI worker (queue → check → points → feedback) ----
    print("\n=== 15. Background AI worker ===")
    sent_feedback: list[int] = []

    async def fake_check(homework, text, images, lang):
        await asyncio.sleep(0.05)          # simulate the AI round-trip
        return CheckResult(ok=True, score=92, grade="A", verdict="correct",
                           summary="Excellent work.")

    async def fake_feedback(bot, submission, homework, student, points, lang,
                            reply_to=None):
        sent_feedback.append(submission.id)

    real_check = ai_worker_module.check_submission
    real_feedback = notifier.send_feedback
    ai_worker_module.check_submission = fake_check
    notifier.send_feedback = fake_feedback
    worker = ai_worker_module.AIWorker(bot=SimpleNamespace(), max_parallel=2, max_queue=4)
    try:
        worker.start()
        async with session_scope() as session:
            fresh_hw = await homework_service.create(
                session, CHAT_ID, "Worker test", "Write 3 sentences.",
                due_at=now() + timedelta(hours=2), created_by=TEACHER_ID,
            )
            fresh_sub = await submission_service.upsert(
                session, fresh_hw, 103, "She goes to school every day.", None,
                "text", 9911,
            )
            fresh_id, attempts, hw_id = fresh_sub.id, fresh_sub.attempts or 1, fresh_hw.id
            before_total = await scoring.total(session, CHAT_ID, 103)
            check("worker accepts a queued job",
                  worker.submit(CheckJob(homework_id=hw_id, submission_id=fresh_id,
                                         chat_id=CHAT_ID, student_id=103, lang="en",
                                         attempts=attempts, text=fresh_sub.content,
                                         reply_to=9911)) is True)
        await asyncio.wait_for(worker._queue.join(), timeout=15)
        check("background job checked without blocking the handler",
              worker.processed == 1, f"processed={worker.processed}")

        async with session_scope() as session:
            stored = await submission_service.get_by_id(session, fresh_id)
            gained = round(await scoring.total(session, CHAT_ID, 103) - before_total, 2)
        check("verdict stored by the worker",
              stored.status == "checked" and stored.ai_score == 92,
              f"{stored.status}/{stored.ai_score}")
        check("points awarded exactly once by the worker",
              gained == 2.0, f"delta={gained}")
        check("feedback sent after the transaction closed",
              sent_feedback == [fresh_id], str(sent_feedback))

        # a crashing AI call must keep the work 'pending' (nothing is lost)
        async def broken_check(homework, text, images, lang):
            raise RuntimeError("AI exploded")

        import logging as _logging

        worker_log = _logging.getLogger("app.ai_worker")
        old_level = worker_log.level
        worker_log.setLevel(_logging.CRITICAL)   # the traceback is expected here
        ai_worker_module.check_submission = broken_check
        try:
            async with session_scope() as session:
                other_sub = await submission_service.upsert(
                    session, fresh_hw, 102, "I is go to school", None, "text", 9912
                )
                other_id, other_attempts = other_sub.id, other_sub.attempts or 1
            worker.submit(CheckJob(homework_id=hw_id, submission_id=other_id,
                                   chat_id=CHAT_ID, student_id=102, lang="en",
                                   attempts=other_attempts, text=other_sub.content))
            await asyncio.wait_for(worker._queue.join(), timeout=15)
            async with session_scope() as session:
                stuck = await submission_service.get_by_id(session, other_id)
            check("a failed AI call keeps the work pending for /pending",
                  stuck.status == "pending" and worker.failed == 1,
                  f"status={stuck.status} failed={worker.failed}")
        finally:
            ai_worker_module.check_submission = real_check
            worker_log.setLevel(old_level)

        # an already-graded submission must not be overwritten by a stale job
        async with session_scope() as session:
            graded = await submission_service.get_by_id(session, fresh_id)
            graded.status = "manual"
            graded.ai_score = 60
            await session.flush()
        worker.submit(CheckJob(homework_id=hw_id, submission_id=fresh_id,
                               chat_id=CHAT_ID, student_id=103, lang="en",
                               attempts=attempts, text="ignored"))
        worker.submit(CheckJob(homework_id=hw_id, submission_id=fresh_id,
                               chat_id=CHAT_ID, student_id=103, lang="en",
                               attempts=attempts + 5, text="also ignored"))
        await asyncio.wait_for(worker._queue.join(), timeout=15)
        async with session_scope() as session:
            after = await submission_service.get_by_id(session, fresh_id)
        check("stale jobs never overwrite a human grade",
              worker.processed == 1 and after.status == "manual" and after.ai_score == 60,
              f"processed={worker.processed} {after.status}/{after.ai_score}")
    finally:
        await worker.stop()
        ai_worker_module.check_submission = real_check
        notifier.send_feedback = real_feedback
    check("worker stops cleanly", worker._task is None)

    # --- 16. AI request retry (transient vs permanent errors) --------------
    print("\n=== 16. AI request retry ===")
    real_delays = ai_checker.RETRY_DELAYS
    ai_checker.RETRY_DELAYS = (0.0, 0.0)      # no sleeping inside the test

    class _RateLimited(Exception):
        status_code = 429

    class _BadKey(Exception):
        status_code = 401

    class _Completions:
        def __init__(self, error: Exception | None = None, succeed_on: int = 99):
            self.calls = 0
            self._error = error
            self._succeed_on = succeed_on

        async def create(self, **kwargs):
            self.calls += 1
            if self.calls < self._succeed_on:
                # `error` is already an exception instance — raise it as-is
                raise self._error if self._error is not None else RuntimeError("temporary")
            return SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(
                    content='{"score": 70, "verdict": "partial"}'))])

    def _client_with(completions) -> SimpleNamespace:
        return SimpleNamespace(chat=SimpleNamespace(completions=completions))

    import logging as _log

    ai_log = _log.getLogger("app.ai_checker")
    old_ai_level, ai_log.level = ai_log.level, _log.CRITICAL  # failures are expected
    try:
        flaky = _Completions(error=_RateLimited(), succeed_on=3)
        payload = await ai_checker._request(
            _client_with(flaky), "m", [{"role": "user", "content": "x"}])
        check("a 429 is retried until it works",
              payload.get("score") == 70 and flaky.calls == 3, f"calls={flaky.calls}")

        broken = _Completions(error=_BadKey())
        raised = False
        try:
            await ai_checker._request(_client_with(broken), "m", [])
        except Exception:
            raised = True
        check("a permanent 401 fails fast (one call, no retries)",
              raised and broken.calls == 1, f"calls={broken.calls}")
    finally:
        ai_checker.RETRY_DELAYS = real_delays
        ai_log.setLevel(old_ai_level)

    # --- 17. AI output normalisation (score ↔ verdict ↔ severity) -----
    print("\n=== 17. AI output normalisation ===")
    fixed = ai_checker._normalise(
        {"score": 1, "verdict": "partial", "summary": "x",
         "mistakes": [
             {"original": "alot", "correction": "a lot", "severity": "minor",
              "explanation": "two words"},
             {"original": "He go", "correction": "He goes", "severity": "major",
              "explanation": "3rd person"},
         ],
         "task_results": [{"task": "Ex.1", "status": "ok"},
                          {"task": "Ex.2", "status": "??? "},
                          {"task": "Ex.3", "status": "not done"}]}
    )
    check("a too-low score is lifted into the verdict's band",
          fixed.score == 50, f"score={fixed.score}")
    check("grade always matches the corrected score", fixed.grade == "D",
          fixed.grade)
    high = ai_checker._normalise({"score": 97, "verdict": "correct"})
    check("a correct verdict keeps a high score", high.score == 97, str(high.score))
    wrong = ai_checker._normalise({"score": 97, "verdict": "wrong"})
    check("a wrong verdict never shows a top score", wrong.score == 49,
          str(wrong.score))
    unclear = ai_checker._normalise({"score": 65, "verdict": "unclear"})
    check("an unclear photo earns no score", unclear.score == 0 and
          unclear.verdict == "unclear", f"{unclear.score}/{unclear.verdict}")
    severities = [m["severity"] for m in fixed.mistakes]
    check("major mistakes are listed before minor ones",
          severities == ["major", "minor"], str(severities))
    statuses = [row["status"] for row in fixed.tasks]
    check("task statuses are normalised",
          statuses == ["correct", "partial", "missing"], str(statuses))
    derived = ai_checker._normalise({"score": 92})
    check("a missing verdict is derived from the score",
          derived.verdict == "correct", derived.verdict)

    # --- 18. Voice answers and confirmation -----------------------------
    print("\n=== 18. Voice answers and confirmation ===")
    from app import deeplink, stt

    check("voice transcripts and captions merge",
          stt.combine("  see photo  ", " I go ") == "see photo I go")
    check("voice size guard blocks monsters",
          stt.too_large(30 * 1024 * 1024) and not stt.too_large(64))
    check("deep links survive a round trip",
          deeplink.parse_parent_payload(
              deeplink.build_parent_payload(-1001234567890, 101))
          == (-1001234567890, 101))
    check("deep links reject junk",
          deeplink.parse_parent_payload("parent_x_y") is None)
    check("parent links need the bot name",
          deeplink.parent_url("@tb", -1001234567890, 101)
          == "https://t.me/tb?start=parent_1001234567890_101"
          and deeplink.parent_url("", -1001234567890, 101) == "")

    async with session_scope() as session:
        homework = await homework_service.create(
            session, CHAT_ID, "Voice test", due_at=now() + timedelta(hours=1),
            created_by=TEACHER_ID,
        )
        parked = await submission_service.upsert(
            session, homework, 103, "I go", None, "voice", 9101)
        # CONFIRM_SUBMISSIONS mode: the work is parked until the student taps ✅
        await submission_service.mark_awaiting(session, parked)
        check("parked work is hidden from /pending",
              parked.id not in {r.id for r in
                                await submission_service.pending(session, CHAT_ID)})
        parked_id, park_homework = parked.id, parked.homework_id
        await submission_service.confirm(session, parked)
    async with session_scope() as session:
        back = await submission_service.get_by_id(session, parked_id)
        check("the student's ✅ returns it to the queue", back.status == "pending")

    # a *different* homework + student, so the parked row above stays intact
    async with session_scope() as session:
        draft_homework = await homework_service.create(
            session, CHAT_ID, "Voice test 2", due_at=now() + timedelta(hours=1))
        loose = await submission_service.upsert(
            session, draft_homework, 101, "draft", None, "voice", 9102)
        await submission_service.mark_awaiting(session, loose)
        loose_id = loose.id
        await submission_service.cancel(session, loose)
    async with session_scope() as session:
        check("the student's ❌ removes the parked row",
              await submission_service.get_by_id(session, loose_id) is None)
    # the deadline never penalises a student whose work was parked in time
    async with session_scope() as session:
        homework = await homework_service.get(session, park_homework, CHAT_ID)
        homework.due_at = now() - timedelta(minutes=1)
        await submission_service.mark_awaiting(
            session, await submission_service.get_by_id(session, parked_id))
    async with session_scope() as session:
        homework = await homework_service.get(session, park_homework, CHAT_ID)
        outcome = await close_homework_and_penalise(_SendOnlyBot(), session, homework)
        pending_row = await submission_service.get_by_id(session, parked_id)
        missing_ids = {entry["student"].tg_id for entry in outcome}
        check("deadline closes parked work as sent, not missing",
              103 not in missing_ids and pending_row.status == "pending",
              f"missing={sorted(missing_ids)} status={pending_row.status}")

    # --- 19. Mini app HTTP layer ----------------------------------------
    print("\n=== 19. Mini app HTTP layer ===")
    from app import miniapp as miniapp_module

    async def _http(path: str, token: str | None = None):
        import urllib.error
        import urllib.request

        request = urllib.request.Request(
            f"http://127.0.0.1:{port}{path}")
        if token:
            request.add_header("X-Auth-Token", token)
        try:
            got = await asyncio.to_thread(urllib.request.urlopen, request,
                                          timeout=10)
            with got:
                return got.status, got.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read() or b""

    mini = miniapp_module.MiniApp(asyncio.get_event_loop(), "127.0.0.1",
                                  port, MINI_TOKEN)
    mini.start()
    try:
        code, body = await _http("/healthz")
        check("health endpoint answers for Render / uptime pings",
              code == 200 and b'"ok"' in body, str(code))
        code, body = await _http("/")
        check("mini app serves its dashboard page",
              code == 200 and b"Students this week" in body, str(code))
        code, _body = await _http(f"/api/summary?chat={CHAT_ID}")
        check("summary API rejects a missing token", code == 401, str(code))
        code, _body = await _http(f"/api/summary?chat={CHAT_ID}&token=nope")
        check("summary API rejects a wrong token", code == 401, str(code))
        code, body = await _http(f"/api/summary?chat={CHAT_ID}&token={MINI_TOKEN}")
        payload = json.loads(body) if code == 200 else {}
        check("summary API returns the weekly numbers",
              code == 200 and payload.get("totals", {}).get("students", 0) > 0,
              str(code))
        code, body = await _http(f"/api/groups?token={MINI_TOKEN}")
        listing = json.loads(body) if code == 200 else {}
        check("group picker list is served (bare URL / menu button)",
              code == 200 and any(g["id"] == CHAT_ID
                                  for g in listing.get("groups", [])),
              str(code))
        code, _body = await _http("/api/groups?token=wrong")
        check("group picker is token guarded", code == 401, str(code))
        code, _body = await _http(f"/api/nope?token={MINI_TOKEN}")
        check("unknown API paths are 404", code == 404, str(code))
    finally:
        mini.stop()
    check("mini app server starts and stops", True)

    print("\n" + "=" * 64)
    if FAILURES:
        print(f"X  {len(FAILURES)} check(s) FAILED:")
        for item in FAILURES:
            print(f"   - {item}")
        return 1
    print("OK  All checks passed — the whole pipeline works offline.")
    return 0


async def main() -> int:
    print("Teacher Bot — offline self-test (no Telegram token, no AI key)")
    db_path = settings.db_path
    if db_path.exists():
        db_path.unlink()
    await init_db()
    try:
        code = await scenario()
    finally:
        await dispose()
    return code


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))


