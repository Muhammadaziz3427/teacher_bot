"""Mirror the SQLite database to a *private* GitHub repository.

Ephemeral hosts (Render free instances, containers without a disk) lose
``data/teacher_bot.db`` on every restart, redeploy **and** spin-down. This
module keeps a zipped copy of the database in a private repo:

* ``pull()`` — restore it on startup when the local file is missing;
* ``push()`` — save it (periodically via the scheduler, and on shutdown);
  a push is skipped when the database has not changed since the last one.

Configuration (Render → Environment):

    DB_SYNC_REPO=owner/private_data_repo     # PRIVATE repo!
    DB_SYNC_TOKEN=ghp_...                    # PAT with Contents: read+write
    DB_SYNC_BRANCH=main                      # optional
    DB_SYNC_INTERVAL=5                       # minutes between checks

CLI:  python -m app.db_sync pull|push|status

A public repo would leak student names, marks and guardians' contacts —
never point ``DB_SYNC_REPO`` at a public repository.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import sqlite3
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Optional

from .config import settings
from .utils import now

log = logging.getLogger(__name__)

API = "https://api.github.com/repos/{repo}/contents/{path}"

_LAST_FINGERPRINT: Optional[tuple[int, int]] = None
_LAST_REMOTE_SHA: Optional[str] = None

#: possible results of :func:`pull`
PULL_OFF = "off"            # DB_SYNC_* is not configured
PULL_LOCAL = "local"        # a local database exists — nothing to do
PULL_RESTORED = "restored"  # downloaded from GitHub
PULL_EMPTY = "empty"        # the repo has no copy yet (very first run)
PULL_ERROR = "error"        # GitHub could not be asked (network/token)


def configured() -> bool:
    return settings.db_sync_ready


def _fingerprint(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_size


def _url(path: Optional[str] = None, ref: bool = False) -> str:
    url = API.format(repo=settings.db_sync_repo,
                     path=path or settings.db_sync_path)
    return f"{url}?ref={settings.db_sync_branch}" if ref else url


def _classify_pull_error(code: int) -> str:
    """A missing file is NOT a failure — it just means "first run".

    404 is returned both for an empty repository and for a repository this
    token cannot see; in both cases the remote has nothing we could
    overwrite, so starting with an empty database is safe.
    """
    return PULL_EMPTY if code == 404 else PULL_ERROR


def _hint(exc: urllib.error.HTTPError) -> str:
    """Human explanation for the mistakes people actually make here."""
    if exc.code in (401, 403):
        return ("GitHub rejected the token — create a new fine-grained PAT with "
                "'Contents: Read and write' on the data repository (also check "
                "that it has not expired)")
    if exc.code == 404:
        return (f"'{settings.db_sync_repo}' or the file was not found — check the "
                "'owner/repo' spelling and that the token can see that repository")
    if exc.code == 422:
        return "GitHub refused the update (stale version) — retrying once"
    return ""


def _request(method: str, url: str, payload: Optional[dict[str, Any]] = None,
             raw_json: bool = False) -> Any:
    data = None
    headers = {
        "Authorization": f"Bearer {settings.db_sync_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "teacher-bot",
    }
    if payload is not None:
        data = (payload if raw_json
                else json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        note = _hint(exc)
        if note:
            log.warning("DB sync: %s (HTTP %s)", note, exc.code)
        raise


def snapshot_zip() -> bytes:
    """An isolated copy of the live database, zipped (WAL is checkpointed)."""
    database = settings.db_path
    temp = database.with_suffix(".snapshot.tmp")
    origin = sqlite3.connect(database)
    try:
        copy = sqlite3.connect(temp)
        try:
            origin.execute("PRAGMA wal_checkpoint(FULL)")
            origin.backup(copy)
        finally:
            copy.close()
    finally:
        origin.close()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.write(temp, "teacher_bot.db")
    temp.unlink(missing_ok=True)
    return buffer.getvalue()


def restore_zip(payload: bytes) -> Path:
    """Write an archive produced by snapshot_zip() over the local database."""
    database = settings.db_path
    database.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(payload)) as bundle:
        member = "teacher_bot.db" if "teacher_bot.db" in bundle.namelist() else bundle.namelist()[0]
        temp = database.with_suffix(".restore.tmp")
        temp.write_bytes(bundle.read(member))
    os.replace(temp, database)
    return database


def pull() -> str:
    """Restore the database from GitHub — see the ``PULL_*`` constants."""
    global _LAST_REMOTE_SHA
    if not configured():
        return PULL_OFF
    if settings.db_path.exists():
        return PULL_LOCAL
    try:
        info = _request("GET", _url(ref=True)) or {}
    except urllib.error.HTTPError as exc:
        return _classify_pull_error(exc.code)
    except Exception as exc:
        log.warning("DB sync: GitHub is unreachable (%s: %s)",
                    type(exc).__name__, exc)
        return PULL_ERROR

    content = info.get("content") or ""
    if not content:
        log.warning("DB sync: the remote file has no readable content")
        return PULL_ERROR
    restore_zip(base64.b64decode(content))
    _LAST_REMOTE_SHA = info.get("sha")
    log.info("DB sync: database restored from %s", settings.db_sync_repo)
    return PULL_RESTORED


def push(force: bool = False) -> bool:
    """Upload the database; skipped when nothing changed since the last push."""
    global _LAST_FINGERPRINT, _LAST_REMOTE_SHA
    if not configured() or not settings.db_path.exists():
        return False
    fingerprint = _fingerprint(settings.db_path)
    if not force and fingerprint == _LAST_FINGERPRINT:
        return False
    payload = snapshot_zip()            # snapshot BEFORE touching the network

    sha: Optional[str] = _LAST_REMOTE_SHA
    try:
        sha = (_request("GET", _url(ref=True)) or {}).get("sha") or sha
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise

    body: dict[str, Any] = {
        "message": f"sync {now().strftime('%Y-%m-%d %H:%M:%S')}",
        "branch": settings.db_sync_branch,
        "content": base64.b64encode(payload).decode("ascii"),
    }
    if sha:
        body["sha"] = sha
    try:
        info = _request("PUT", _url(), body)
    except urllib.error.HTTPError as exc:
        if exc.code not in {409, 422}:       # stale sha → one refresh attempt
            raise
        sha = (_request("GET", _url(ref=True)) or {}).get("sha")
        if not sha:
            return False
        body["sha"] = sha
        info = _request("PUT", _url(), body)

    _LAST_REMOTE_SHA = (info or {}).get("sha")
    _LAST_FINGERPRINT = _fingerprint(settings.db_path)
    log.info("DB sync: pushed %s bytes to %s",
             len(payload), settings.db_sync_repo)
    return True


async def push_async(force: bool = False) -> bool:
    """Never block the event loop (the HTTP call is synchronous)."""
    import asyncio

    return await asyncio.to_thread(push, force)


async def pull_async() -> str:
    import asyncio

    return await asyncio.to_thread(pull)


def status(live: bool = False) -> dict[str, Any]:
    """Configuration + (optionally) a live read of the remote file."""
    info: dict[str, Any] = {
        "configured": configured(),
        "repo": settings.db_sync_repo,
        "branch": settings.db_sync_branch,
        "path": settings.db_sync_path,
        "interval_minutes": settings.db_sync_interval,
        "local_db": str(settings.db_path),
        "local_exists": settings.db_path.exists(),
        "last_pushed_sha": _LAST_REMOTE_SHA,
    }
    if live and configured():
        try:
            data = _request("GET", _url(ref=True)) or {}
            info["remote"] = {"reachable": True, "sha": data.get("sha"),
                              "size": data.get("size")}
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                info["remote"] = {"reachable": True,
                                  "file": "not uploaded yet (will be created)"}
            else:
                info["remote"] = {"reachable": False,
                                  "error": f"HTTP {exc.code} — {_hint(exc)}"}
        except Exception as exc:
            info["remote"] = {"reachable": False,
                              "error": f"{type(exc).__name__}: {exc}"}
    return info


def _main(argv: list[str]) -> int:
    import asyncio

    if not configured():
        print("DB_SYNC_REPO / DB_SYNC_TOKEN are not set — nothing to do.")
        return 1
    command = (argv[1] if len(argv) > 1 else "status").lower()
    if command == "status":
        # live check: proves the repo + token actually work, before you rely on it
        print(json.dumps(status(live=True), indent=2, ensure_ascii=False))
        return 0
    if command == "pull":
        state = pull()
        print({"off": "DB_SYNC_* is not configured",
               "local": "skipped — a local database already exists",
               "restored": "restored from GitHub",
               "empty": "nothing to restore yet (the repo has no copy)",
               "error": "could not reach GitHub — see the warning above"}.get(state, state))
        return 0 if state != PULL_ERROR else 1
    if command == "push":
        changed = push(force="--force" in argv)
        print("pushed" if changed else "skipped (no changes)")
        return 0
    print("usage: python -m app.db_sync [pull|push|status]")
    return 2


if __name__ == "__main__":                # pragma: no cover
    import sys

    raise SystemExit(_main(sys.argv))
