"""Background AI checking.

The Telegram handler only *saves* the submission and puts a job on this
queue; the AI call itself happens here, outside of any DB transaction:

    load (short session) → AI call (no session) → save (short session) → notify

That keeps SQLite transactions short (no 90-second locks), limits how many
AI calls may run at once and makes the bot answer students immediately.
Jobs that cannot be finished stay ``pending`` and show up in ``/pending``.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

from aiogram import Bot

from .ai_checker import check_submission
from .db import session_scope
from .i18n import t
from .services import homework as homework_service
from .services import notifier
from .services import scoring
from .services import students as student_service
from .services import submissions as submission_service

log = logging.getLogger(__name__)

MAX_PARALLEL = 5     # how many AI calls may run at the same time
MAX_QUEUE = 100      # how many submissions may wait for a free slot


@dataclass(slots=True)
class CheckJob:
    """Everything the worker needs, captured while the handler session is open."""

    homework_id: int
    submission_id: int
    chat_id: int
    student_id: int
    lang: str
    attempts: int
    text: str = ""
    images: list[tuple[bytes, str]] = field(default_factory=list)
    reply_to: Optional[int] = None


class AIWorker:
    def __init__(
        self,
        bot: Bot,
        max_parallel: int = MAX_PARALLEL,
        max_queue: int = MAX_QUEUE,
    ) -> None:
        self._bot = bot
        self._queue: asyncio.Queue[CheckJob] = asyncio.Queue(maxsize=max_queue)
        self._limit = asyncio.Semaphore(max_parallel)
        self._task: Optional[asyncio.Task] = None
        self.processed = 0
        self.failed = 0

    # --- lifecycle -----------------------------------------------------
    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="ai-worker")
            log.info("AI worker started (max_parallel=%s, max_queue=%s)",
                     MAX_PARALLEL, self._queue.maxsize)

    async def stop(self) -> None:
        """Cancel the worker. Unfinished jobs stay 'pending' (see /pending)."""
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        log.info("AI worker stopped (%s checked, %s failed)",
                 self.processed, self.failed)

    # --- producer ------------------------------------------------------
    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    def submit(self, job: CheckJob) -> bool:
        """Queue a job; False means the queue is full (caller should retry)."""
        try:
            self._queue.put_nowait(job)
        except asyncio.QueueFull:
            return False
        return True

    # --- consumer ------------------------------------------------------
    async def _run(self) -> None:
        while True:
            job = await self._queue.get()
            try:
                async with self._limit:
                    await self._handle(job)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.failed += 1
                log.exception("AI check failed for submission %s", job.submission_id)
            finally:
                self._queue.task_done()


    async def _handle(self, job: CheckJob) -> None:
        # 1) short transaction: read the rows we need
        async with session_scope() as session:
            submission = await submission_service.get_by_id(session, job.submission_id)
            homework = await homework_service.get(session, job.homework_id, job.chat_id)
            student = await student_service.get_user(session, job.chat_id, job.student_id)
            if submission is None or homework is None or student is None:
                log.info("AI job dropped: submission %s no longer exists", job.submission_id)
                return
            if not _is_current(submission, job):
                log.info("AI job skipped: submission %s was graded or re-sent",
                         job.submission_id)
                return
            student_name = student.full_name

        # 2) the AI call itself — no DB transaction is open here
        result = await check_submission(homework, job.text, job.images, job.lang)
        if not result.ok:
            log.warning("AI unavailable for submission %s: %s",
                        job.submission_id, (result.error or result.summary)[:200])

        # 3) short transaction: store the verdict (only if still up to date)
        points = 0.0
        graded = False
        async with session_scope() as session:
            submission = await submission_service.get_by_id(session, job.submission_id)
            if submission is None or not _is_current(submission, job):
                log.info("AI result discarded: submission %s changed meanwhile",
                         job.submission_id)
            else:
                await submission_service.apply_result(session, submission, result)
                if result.ok:
                    points = await scoring.award_for_submission(
                        session, submission, homework, result,
                        homework.chat_id, submission.student_id,
                    )
                graded = True

        if not graded:
            return
        self.processed += 1

        # 4) report — outside of any transaction, the verdict is already saved
        try:
            await notifier.send_feedback(
                self._bot, submission, homework, student, points,
                job.lang, reply_to=job.reply_to,
            )
        except Exception:
            log.exception("Could not send feedback for submission %s", job.submission_id)

        if not result.ok:
            await self._notify_teachers(job, student_name)

    async def confirm_deadline_rows(
        self, session, homework, lang: str
    ) -> int:
        """The deadline passed: every parked submission counts as sent.

        Rows are flipped to ``pending`` (so they are neither penalised nor
        forgotten) and queued for the AI like any other submission.
        """
        queued = 0
        for row in await submission_service.awaiting(session, homework.id):
            await submission_service.confirm(session, row)
            try:
                images = await self._bot_download_photo(row)
                if self.submit(CheckJob(
                    homework_id=homework.id,
                    submission_id=row.id,
                    chat_id=homework.chat_id,
                    student_id=row.student_id,
                    lang=lang,
                    attempts=row.attempts or 1,
                    text=row.content or "",
                    images=images,
                    reply_to=row.message_id,
                )):
                    queued += 1
            except Exception:
                log.exception("Could not queue deadline submission %s", row.id)
        return queued

    async def _bot_download_photo(self, submission) -> list[tuple[bytes, str]]:
        """Re-fetch the single stored photo (confirm mode only stores one)."""
        if not submission.media_file_id or submission.media_type != "photo":
            return []
        try:
            buffer = await self._bot.download(submission.media_file_id)
        except Exception:
            return []
        if buffer is None:
            return []
        return [(buffer.read(), "image/jpeg")]

    async def _notify_teachers(self, job: CheckJob, student_name: str) -> None:
        """Tell the teachers that a human grade is needed (/pending)."""
        async with session_scope() as session:
            users = await student_service.all_users(session, job.chat_id)
            teachers = [u for u in users if u.role in {"teacher", "admin"}]
        for teacher in teachers:
            try:
                await self._bot.send_message(
                    teacher.tg_id,
                    t("fb_pending_teacher", job.lang,
                      id=job.submission_id, name=notifier.esc(student_name)),
                )
            except Exception:
                continue


def _is_current(submission, job: CheckJob) -> bool:
    """True when nobody graded it and no newer attempt replaced it."""
    return (
        submission.status == "pending"
        and (submission.attempts or 1) == job.attempts
    )


# --------------------------------------------------------------------------
# Module-level singleton (handlers and main.py share it)
# --------------------------------------------------------------------------
_worker: Optional[AIWorker] = None


def setup_worker(bot: Bot) -> AIWorker:
    global _worker
    _worker = AIWorker(bot)
    return _worker


def get_worker() -> AIWorker:
    if _worker is None:
        raise RuntimeError("AI worker is not set up — call setup_worker() first")
    return _worker
