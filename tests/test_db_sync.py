"""DB mirroring for ephemeral hosts (Render free): GitHub as storage."""
from __future__ import annotations

import io
import sqlite3
import zipfile

from app import db_sync
from app.config import settings


def test_not_configured_by_default():
    # conftest.py never sets DB_SYNC_REPO / DB_SYNC_TOKEN
    assert db_sync.configured() is False
    assert db_sync.status()["configured"] is False


def test_pull_and_push_are_safe_noops_without_configuration():
    assert db_sync.pull() == db_sync.PULL_OFF
    assert db_sync.push() is False
    assert db_sync.push(force=True) is False     # never touches the network


def test_a_missing_remote_file_is_a_first_run_not_an_error():
    """Render free starts with an empty data repo — that must not block boot."""
    assert db_sync._classify_pull_error(404) == db_sync.PULL_EMPTY
    for code in (401, 403, 500, 502):
        assert db_sync._classify_pull_error(code) == db_sync.PULL_ERROR


def test_pull_states_are_distinct():
    states = {db_sync.PULL_OFF, db_sync.PULL_LOCAL, db_sync.PULL_RESTORED,
              db_sync.PULL_EMPTY, db_sync.PULL_ERROR}
    assert len(states) == 5


def test_status_reports_the_local_database():
    info = db_sync.status()
    assert info["repo"] == ""
    assert info["path"].endswith(".zip")
    assert info["local_db"].endswith("pytest.db")


def test_error_hints_explain_common_mistakes():
    """Worst-case debugging help: the log must name the actual fix."""
    import urllib.error

    def err(code):
        return urllib.error.HTTPError("url", code, "msg", {}, None)  # type: ignore[arg-type]

    assert "Contents" in db_sync._hint(err(401))
    assert "Contents" in db_sync._hint(err(403))
    assert "owner/repo" in db_sync._hint(err(404))
    assert db_sync._hint(err(500)) == ""


def test_live_status_stays_offline_when_not_configured():
    info = db_sync.status(live=True)
    assert "remote" not in info          # no token → no network call


def test_snapshot_is_a_zipped_sqlite_database():
    database = settings.db_path
    if not database.exists():                    # runs before the DB tests
        conn = sqlite3.connect(database)
        conn.execute("CREATE TABLE IF NOT EXISTS sample (x INTEGER)")
        conn.commit()
        conn.close()

    payload = db_sync.snapshot_zip()
    with zipfile.ZipFile(io.BytesIO(payload)) as bundle:
        assert "teacher_bot.db" in bundle.namelist()
        dumped = bundle.read("teacher_bot.db")
    assert dumped.startswith(b"SQLite format 3\x00")


def test_restore_round_trip():
    database = settings.db_path
    payload = db_sync.snapshot_zip()
    restored = db_sync.restore_zip(payload)      # same bytes come back
    assert restored == database
    conn = sqlite3.connect(database)
    try:
        conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
    finally:
        conn.close()