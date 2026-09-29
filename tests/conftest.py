"""Test bootstrap: import path + a throwaway database.

Env vars are set BEFORE any ``app.*`` import so ``app.config`` (which reads
``.env``) can never point the tests at the real database or a live AI.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Force an isolated DB (not setdefault — a developer's .env must not win)
os.environ["DB_FILE"] = "data/pytest.db"
os.environ.setdefault("AI_ENABLED", "false")
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("AUTO_WEEKLY_REPORT", "false")
os.environ.setdefault("BOT_TOKEN", "")


@pytest.fixture(scope="session", autouse=True)
def _fresh_database():
    """Delete the throwaway DB once per test session (WAL sidecars too)."""
    db = ROOT / "data" / "pytest.db"
    for path in (db, Path(str(db) + "-wal"), Path(str(db) + "-shm")):
        path.unlink(missing_ok=True)
    yield