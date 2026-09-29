"""Background jobs: deadline closing, reminders, weekly reports."""

from __future__ import annotations

import logging

from datetime import datetime

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from .config import settings
from . import db_sync
from .db import session_scope
from .models import Chat, Homework
from .services import homework as homework_service
from .services import notifier
from .services import reports as reports_service
from .services import scoring
from .services import students as student_service
from .services import submissions as submission_service
from .services import tests as tests_service
from .services import topics as topic_service
from .utils import now, parse_time

try:    # the worker is optional here: jobs may run without it (tests)
    from .ai_worker import get_worker
except ImportError:
    get_worker = None  # type: ignore[assignment]

log = logging.getLogger(__name__)


async def language_of(session, chat_id: int) -> str:
    chat = await session.get(Chat, chat_id)
    return (chat.language if chat and chat.language else "bi")


async def close_homework_and_penalise(
    bot: Bot, session, homework: Homework, lang: str | None = None
) -> list[dict]:
    """
    Close a homework, penalise everyone who did not submit, escalate repeat
    offenders (warning → AI extra task) and post the list in the group.
    """
    lang = lang or await language_of(session, homework.chat_id)
    # CONFIRM_SUBMISSIONS: a parked ("confirm") row still counts as sent —
    # the deadline closes it and queues it for the AI instead of penalising.
    confirmed = await _auto_confirm_parked(session, homework, lang)
    if confirmed:
        log.info("Auto-confirmed %s parked submission(s) for homework %s",
                 confirmed, homework.id)
    submitted = await submission_service.submitted_ids(session, homework.id)
    students = await student_service.list_students(session, homework.chat_id)
    missing = [student for student in students if student.tg_id not in submitted]
    await homework_service.close(session, homework)
    if not missing:
        return []
    outcome = await scoring.apply_missing(session, homework, missing, lang)
    try:
        await notifier.send_missing_report(bot, homework, outcome, lang)
    except Exception:  # never let a send failure kill the job
        log.exception("Could not post the missing-homework report")
    return outcome


async def _auto_confirm_parked(session, homework: Homework, lang: str) -> int:
    """Flip parked rows to pending and hand them to the AI worker.

    With CONFIRM_SUBMISSIONS on, a student who sent work but never pressed ✅
    is still not a "missing" student: the deadline closes their work and the
    worker checks it like any other submission.
    """
    if get_worker is not None:
        try:
            return await get_worker().confirm_deadline_rows(session, homework, lang)
        except RuntimeError:
            pass    # worker not started (e.g. in tests) — confirm inline below
    rows = await submission_service.awaiting(session, homework.id)
    for row in rows:
        await submission_service.confirm(session, row)
    return len(rows)


async def check_deadlines(bot: Bot) -> None:
    """Every minute: close everything whose deadline has passed."""
    async with session_scope() as session:
        for homework in await homework_service.due_soon(session, now()):
            try:
                await close_homework_and_penalise(bot, session, homework)
            except Exception:
                log.exception("Deadline job failed for homework %s", homework.id)


async def send_due_reminders(bot: Bot) -> None:
    """Remind the group 24h and 1h before the deadline (once per threshold)."""
    async with session_scope() as session:
        for homework in await homework_service.active_all(session):
            hours_left = (homework.due_at - now()).total_seconds() / 3600
            if hours_left <= 0:
                continue
            lang = await language_of(session, homework.chat_id)
            sent = list(homework.reminders_sent or [])
            for threshold in sorted(settings.reminder_hours):
                if threshold in sent or hours_left > threshold:
                    continue
                try:
                    await notifier.send_reminder(bot, homework, threshold, lang)
                except Exception:
                    log.exception("Reminder failed for homework %s", homework.id)
                await homework_service.mark_reminded(session, homework, threshold)


async def weekly_report_job(bot: Bot) -> None:
    """Post the weekly report into every class group (and DM the teachers)."""
    async with session_scope() as session:
        chats = (await session.execute(select(Chat))).scalars().all()
        for chat in chats:
            if await student_service.count_students(session, chat.id) == 0:
                continue
            lang = chat.language or "bi"
            try:
                text = await reports_service.group_report(session, chat.id, "weekly", lang)
                thread = topic_service.thread_for(chat, "announcements")
                await notifier.send_long(bot, chat.id, text, thread_id=thread)
            except Exception:
                log.exception("Weekly report failed for chat %s", chat.id)
            await _dm_reports_to_teachers(bot, session, chat, "weekly", lang)


async def _dm_reports_to_teachers(bot: Bot, session, chat: Chat, period: str, lang: str) -> None:
    """Every teacher of a group gets the student reports privately."""
    teachers = await _teacher_ids(session, chat.id)
    if not teachers:
        return
    for student in await student_service.list_students(session, chat.id):
        try:
            text, _ = await reports_service.student_report(
                session, chat.id, student, period, lang
            )
        except Exception:
            continue
        for teacher_id in teachers:
            try:
                await notifier.send_long(bot, teacher_id, text)
            except Exception:
                continue


async def _teacher_ids(session, chat_id: int) -> list[int]:
    """Telegram ids that manage this group (staff rows + config + assignments)."""
    ids: set[int] = set(settings.teacher_ids) | set(settings.admin_ids)
    for user in await student_service.all_users(session, chat_id):
        if user.role in {"teacher", "admin"}:
            ids.add(user.tg_id)
    for row in await student_service.group_managers(session, chat_id):
        ids.add(row.tg_id)
    return sorted(ids)


# --------------------------------------------------------------------------
# Tests: post on schedule, create automatically, close and report results
# --------------------------------------------------------------------------
async def post_due_tests(bot: Bot) -> None:
    """Post every scheduled test whose time has come (into the Test topic)."""
    async with session_scope() as session:
        for test in await tests_service.due_tests(session, now()):
            chat = await session.get(Chat, test.chat_id)
            lang = chat.language if chat and chat.language else "bi"
            try:
                posted = await tests_service.publish_test(bot, session, test, chat, lang)
                if posted:
                    log.info("Posted test #%s (%s questions)", test.id, posted)
            except Exception:
                log.exception("Could not post test %s", test.id)


async def finish_ending_tests(bot: Bot) -> None:
    """Close tests whose answering window ended and post the results."""
    async with session_scope() as session:
        for test in await tests_service.ending_tests(session, now()):
            chat = await session.get(Chat, test.chat_id)
            lang = chat.language if chat and chat.language else "bi"
            try:
                await tests_service.finish_test(bot, session, test, chat, lang)
            except Exception:
                log.exception("Could not finish test %s", test.id)


async def auto_tests_job(bot: Bot) -> None:
    """The bot writes and posts its own test at the time the teacher chose.

    The syllabus comes from the lessons the class has actually been given, so
    the teacher never has to describe the topic.
    """
    async with session_scope() as session:
        moment = now()
        chats = (await session.execute(select(Chat))).scalars().all()
        for chat in chats:
            if chat.test_weekday is None or not chat.test_time:
                continue
            if chat.test_weekday != moment.weekday():
                continue
            if chat.last_test_at and chat.last_test_at.date() == moment.date():
                continue
            scheduled = datetime.combine(
                moment.date(), parse_time(chat.test_time) or moment.time()
            )
            if moment < scheduled or (moment - scheduled).total_seconds() > 3600:
                continue  # not yet, or the window has long passed
            lang = chat.language or "bi"
            try:
                test = await tests_service.build_ai_test(
                    session, chat, lang, chat.test_count or 10,
                    created_by=0, title="Weekly test",
                )
                if test is None:
                    log.info("Auto test skipped for %s (no lessons or AI off)", chat.id)
                    chat.last_test_at = moment
                    await session.flush()
                    continue
                await tests_service.publish_test(bot, session, test, chat, lang)
                chat.last_test_at = moment
                await session.flush()
                log.info("Auto weekly test posted for chat %s", chat.id)
            except Exception:
                log.exception("Auto test failed for chat %s", chat.id)


async def db_sync_job(bot: Bot) -> None:
    """Ephemeral host (Render free): mirror the DB to the private GitHub repo.

    The job itself checks whether the database actually changed, so quiet
    periods cost no API calls and no history in the mirror repository.
    """
    try:
        await db_sync.push_async()
    except Exception:
        log.exception("Database sync to GitHub failed")


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=settings.tz)
    scheduler.add_job(
        check_deadlines,
        IntervalTrigger(minutes=1),
        args=[bot],
        id="deadlines",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        send_due_reminders,
        IntervalTrigger(minutes=5),
        args=[bot],
        id="reminders",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        post_due_tests,
        IntervalTrigger(minutes=1),
        args=[bot],
        id="tests-post",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        finish_ending_tests,
        IntervalTrigger(minutes=1),
        args=[bot],
        id="tests-finish",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        auto_tests_job,
        IntervalTrigger(minutes=5),
        args=[bot],
        id="tests-auto",
        max_instances=1,
        coalesce=True,
    )
    if settings.auto_weekly_report:
        scheduler.add_job(
            weekly_report_job,
            CronTrigger(day_of_week=settings.auto_weekly_day,
                        hour=settings.auto_weekly_hour),
            args=[bot],
            id="weekly-report",
            max_instances=1,
            coalesce=True,
        )
    if settings.db_sync_ready:
        scheduler.add_job(
            db_sync_job,
            IntervalTrigger(minutes=max(1, settings.db_sync_interval)),
            args=[bot],
            id="db-sync",
            max_instances=1,
            coalesce=True,
        )
    scheduler.start()
    log.info("Scheduler started (%s zones, weekly=%s, db_sync=%s)",
             settings.tz_name, settings.auto_weekly_report,
             settings.db_sync_ready)
    return scheduler
