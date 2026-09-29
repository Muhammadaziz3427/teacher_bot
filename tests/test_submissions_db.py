"""Submission lifecycle against a real (throwaway) SQLite database."""
from __future__ import annotations

from datetime import timedelta

import pytest
import pytest_asyncio

from app.ai_checker import CheckResult
from app.db import dispose, init_db, session_scope
from app.services import homework as homework_service
from app.services import students as student_service
from app.services import submissions as submission_service
from app.utils import now

CHAT = -1005550001
STUDENT = 900001


@pytest_asyncio.fixture
async def db():
    await init_db()
    yield
    await dispose()


async def test_resend_creates_a_new_attempt(db):
    async with session_scope() as session:
        homework = await homework_service.create(
            session, CHAT, "Unit 1", "Describe your family",
            due_at=now() + timedelta(hours=2), created_by=1,
        )
        first = await submission_service.upsert(
            session, homework, STUDENT, "answer 1", None, "text", 1001
        )
        assert first.attempts == 1 and first.status == "pending"

        await submission_service.apply_result(
            session, first,
            CheckResult(ok=True, score=92, grade="A", verdict="correct"),
        )
        assert first.status == "checked"

        # the student sends the work again → same row, one more attempt
        again = await submission_service.upsert(
            session, homework, STUDENT, "answer 2", None, "text", 1002
        )
        assert again.id == first.id
        assert again.attempts == 2
        assert again.status == "pending"     # a re-send must be checked again
        assert again.content == "answer 2"


async def test_past_deadline_marks_the_work_late(db):
    async with session_scope() as session:
        homework = await homework_service.create(
            session, CHAT, "Unit 2", due_at=now() - timedelta(minutes=5),
        )
        late = await submission_service.upsert(
            session, homework, STUDENT, "late work", None, "text", 2001
        )
        assert late.is_late is True


async def test_pending_lists_only_ungraded_work(db):
    async with session_scope() as session:
        homework = await homework_service.create(
            session, CHAT, "Unit 3", due_at=now() + timedelta(hours=1),
        )
        fresh = await submission_service.upsert(
            session, homework, STUDENT, "needs grading", None, "text", 3001
        )

    async with session_scope() as session:
        pending_ids = {row.id for row in await submission_service.pending(session, CHAT)}
        assert fresh.id in pending_ids

        # once graded it disappears from the teacher's /pending list
        row = await submission_service.get_by_id(session, fresh.id)
        await submission_service.apply_result(
            session, row, CheckResult(ok=True, score=80, grade="B", verdict="correct")
        )
        pending_ids = {r.id for r in await submission_service.pending(session, CHAT)}
        assert fresh.id not in pending_ids


async def test_confirmation_parkes_and_releases_work(db):
    """Blok 4: the student confirms with ✅ before anything is checked."""
    async with session_scope() as session:
        homework = await homework_service.create(
            session, CHAT, "Unit 4", due_at=now() + timedelta(hours=1),
        )
        row = await submission_service.upsert(
            session, homework, STUDENT, "final version", None, "text", 4001
        )

        # parking: not visible in /pending, counted in the parked list
        await submission_service.mark_awaiting(session, row)
        assert submission_service.is_awaiting(row) is True
        assert {r.id for r in await submission_service.pending(session, CHAT)} \
            .isdisjoint({row.id})
        parked = await submission_service.awaiting(session, homework.id)
        assert {r.id for r in parked} == {row.id}

        # the teacher's grade button has nothing to grab while it is parked
        assert row.status == "confirm"

        # the student's own ✅ releases it back into the normal pipeline
        await submission_service.confirm(session, row)
        assert submission_service.is_awaiting(row) is False
        pending_ids = {r.id for r in await submission_service.pending(session, CHAT)}
        assert row.id in pending_ids


async def test_confirmation_cancel_removes_the_row(db):
    async with session_scope() as session:
        homework = await homework_service.create(
            session, CHAT, "Unit 5", due_at=now() + timedelta(hours=1),
        )
        row = await submission_service.upsert(
            session, homework, STUDENT, "draft", None, "text", 5001
        )
        await submission_service.mark_awaiting(session, row)
        await submission_service.cancel(session, row)
        assert await submission_service.get_by_id(session, row.id) is None


async def test_minapp_summary_payload(db):
    """Blok 4: the dashboard payload is complete and JSON-safe."""
    import json
    from app import miniapp
    from app.services import scoring as scoring_service

    async with session_scope() as session:
        homework = await homework_service.create(
            session, CHAT, "Unit 7", due_at=now() + timedelta(hours=2)
        )
        await student_service.touch_user(
            session, STUDENT, CHAT, "Mini App Student", "miniapp"
        )
        row = await submission_service.upsert(
            session, homework, STUDENT, "dashboard work", None, "text", 7001
        )
        await submission_service.apply_result(
            session, row, CheckResult(ok=True, score=80, grade="B", verdict="correct")
        )
        await scoring_service.award_for_submission(
            session, row, homework,
            CheckResult(ok=True, score=80, grade="B", verdict="correct"),
            CHAT, STUDENT,
        )
        payload = await miniapp.summary(session, CHAT)
    json.dumps(payload)                       # must be JSON-serialisable
    rows = payload["students"]
    assert payload["totals"]["students"] >= 1
    assert payload["totals"]["active_homeworks"] >= 1
    assert payload["totals"]["avg_score"] >= 80.0
    by_id = {s["id"]: s for s in rows}
    assert by_id[STUDENT]["points"] >= 2.0    # +2 for this check, older tests add more


async def test_deadline_auto_confirms_parked_rows(db):
    """Blok 4: parked work is checked at the deadline, never penalised."""
    from app.scheduler import close_homework_and_penalise

    class _FakeBot:
        async def send_message(self, *args, **kwargs):
            return None

        async def send_photo(self, *args, **kwargs):
            return None

    async with session_scope() as session:
        homework = await homework_service.create(
            session, CHAT, "Unit 6", due_at=now() - timedelta(minutes=1),
        )
        row = await submission_service.upsert(
            session, homework, STUDENT, "quiet but sent", None, "text", 6001
        )
        await submission_service.mark_awaiting(session, row)
    async with session_scope() as session:
        homework = await homework_service.get(session, row.homework_id, CHAT)
        await close_homework_and_penalise(_FakeBot(), session, homework)
    async with session_scope() as session:
        closed = await homework_service.get(session, row.homework_id, CHAT)
        submitted = await submission_service.submitted_ids(session, closed.id)
        restored = await submission_service.get_by_id(session, row.id)
        assert closed.status == "closed"
        assert STUDENT in submitted           # counted as sent, not missing
        assert restored.status == "pending"   # queued for the AI worker