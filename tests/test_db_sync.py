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
    assert db_sync.pull() is False
    assert db_sync.push() is False
    assert db_sync.push(force=True) is False     # never touches the network


def test_status_reports_the_local_database():
    info = db_sync.status()
    assert info["repo"] == ""
    assert info["path"].endswith(".zip")
    assert info["local_db"].endswith("pytest.db")


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