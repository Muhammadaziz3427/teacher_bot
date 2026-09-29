"""Teacher dashboard as a Telegram Mini App.

A tiny read-only web app (stdlib only, no extra dependency) that the teacher
opens with one tap from Telegram:

* ``GET /``            → the dashboard page (``miniapp/index.html``)
* ``GET /api/summary`` → JSON for one group, protected by ``MINIAPP_TOKEN``

The HTTP server runs in a daemon thread; every request schedules a coroutine
on the bot's event loop, so the async engine is used exactly as elsewhere.
Turn it on with ``MINIAPP_ENABLED=true`` + ``MINIAPP_TOKEN=<random string>``
and expose the port over HTTPS (reverse proxy or a tunnel) — Telegram only
loads Mini Apps from https:// addresses.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from concurrent.futures import CancelledError as _Cancelled
from .config import settings
from .db import session_scope
from .models import Chat
from .services import attendance as attendance_service
from .services import homework as homework_service
from .services import reports as reports_service
from .services import scoring
from .services import students as student_service
from .services import submissions as submission_service

log = logging.getLogger(__name__)

INDEX_FILE = Path(__file__).resolve().parent.parent / "miniapp" / "index.html"


async def summary(session, chat_id: int) -> dict[str, Any]:
    """The whole dashboard payload: weekly numbers for one group."""
    start, end = reports_service.period_bounds("weekly")
    start_dt, end_dt = reports_service.as_datetimes(start, end)

    students = await student_service.list_students(session, chat_id)
    homeworks = await homework_service.active(session, chat_id)
    points = await scoring.totals_map(session, chat_id, start_dt, end_dt)
    attendance = await attendance_service.group_stats(session, chat_id, start, end)
    submissions = await submission_service.between(session, chat_id, start_dt, end_dt)
    graded = [s.ai_score for s in submissions if s.status in {"checked", "manual"}]

    rows: list[dict[str, Any]] = []
    for student in students:
        counts = attendance.get(student.tg_id, {})
        total = counts.get("total", 0)
        rows.append({
            "id": student.tg_id,
            "name": student.full_name,
            "points": round(points.get(student.tg_id, 0.0), 2),
            "attendance": (round(counts.get("attended", 0) * 100 / total)
                           if total else None),
            "submitted": sum(1 for s in submissions if s.student_id == student.tg_id),
        })
    rows.sort(key=lambda row: row["points"], reverse=True)

    return {
        "group": {"id": chat_id, "title": (await _chat_title(session, chat_id))},
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "students": rows,
        "active_homeworks": [
            {"id": h.id, "title": h.title, "due": h.due_at.strftime("%d.%m %H:%M")}
            for h in homeworks
        ],
        "totals": {
            "students": len(students),
            "active_homeworks": len(homeworks),
            "submitted": len(submissions),
            "avg_score": round(sum(graded) / len(graded), 1) if graded else 0.0,
        },
    }


async def _chat_title(session, chat_id: int) -> str:
    chat = await session.get(Chat, chat_id)
    return chat.title if chat and chat.title else str(chat_id)


async def _summary_for_chat(chat_id: int) -> dict[str, Any]:
    """Runs on the bot's event loop (scheduled from the HTTP thread)."""
    from .db import SessionLocal

    async with SessionLocal() as session:
        return await summary(session, chat_id)


def _make_handler(loop: asyncio.AbstractEventLoop, token: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "TeacherBotMini/1.0"

        def log_message(self, fmt, *args):        # keep the console clean
            log.debug("miniapp %s - %s", self.address_string(), fmt % args)

        def _send(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, payload: dict[str, Any]) -> None:
            self._send(code,
                       json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")

        def do_GET(self) -> None:                  # noqa: N802 - http.server API
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)

            if parsed.path in ("/", "/index.html"):
                if not INDEX_FILE.exists():
                    self._json(500, {"error": "miniapp/index.html is missing"})
                    return
                self._send(200, INDEX_FILE.read_bytes(), "text/html; charset=utf-8")
                return

            if parsed.path != "/api/summary":
                self._json(404, {"error": "not found"})
                return

            given = (query.get("token", [""])[0]
                     or self.headers.get("X-Auth-Token", "")).strip()
            if not token or given != token:
                self._json(401, {"error": "bad token"})
                return

            try:
                chat_id = int(query.get("chat", [""])[0])
            except ValueError:
                self._json(400, {"error": "chat id is required"})
                return

            try:
                future = asyncio.run_coroutine_threadsafe(
                    _summary_for_chat(chat_id), loop
                )
                data = future.result(timeout=15)
            except _Cancelled:
                # the server is stopping: any half-finished handler is dropped
                return
            except concurrent.futures.TimeoutError:
                log.warning("Mini app request timed out for chat %s", chat_id)
                self._json(504, {"error": "the bot is busy, try again"})
                return
            except Exception:
                log.exception("Mini app request failed for chat %s", chat_id)
                self._json(500, {"error": "database error"})
                return
            try:
                self._json(200, data)
            except (BrokenPipeError, ConnectionResetError):
                pass

    return Handler


class MiniApp:
    """A running dashboard server (``stop()`` shuts it down)."""

    def __init__(self, loop: asyncio.AbstractEventLoop, host: str, port: int,
                 token: str) -> None:
        self._loop = loop
        self.host, self.port, self.token = host, port, token
        self._httpd: Optional[ThreadingHTTPServer] = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> None:
        self._httpd = ThreadingHTTPServer(
            (self.host, self.port), _make_handler(self._loop, self.token)
        )
        Thread(target=self._httpd.serve_forever, daemon=True,
               name="miniapp").start()
        log.info("Mini app started at %s (token protected)", self.url)

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
            log.info("Mini app stopped")


def start(loop: Optional[asyncio.AbstractEventLoop] = None) -> Optional[MiniApp]:
    """Start the dashboard; ``None`` when it is switched off or busy."""
    if not settings.miniapp_ready:
        return None
    server = MiniApp(
        loop or asyncio.get_event_loop(),
        settings.miniapp_host, settings.miniapp_port, settings.miniapp_token,
    )
    try:
        server.start()
    except OSError as exc:
        log.warning("Mini app not started on %s:%s — %s",
                    settings.miniapp_host, settings.miniapp_port, exc)
        return None
    return server