"""Async engine, session factory and bootstrap helpers."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import settings
from .models import Base

engine = create_async_engine(settings.db_url, echo=False, future=True)


def _sqlite_pragmas(dbapi_connection, connection_record) -> None:
    """Make SQLite safe for many readers + one writer (bot = scheduler + handlers).

    WAL lets the scheduler poll deadlines while a student's submission is being
    saved; busy_timeout makes a writer wait instead of failing with
    "database is locked" when two updates land at the same moment.
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=5000")
    finally:
        cursor.close()


if engine.dialect.name == "sqlite":
    event.listen(engine.sync_engine, "connect", _sqlite_pragmas)

SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def init_db() -> None:
    """Create all tables (safe to call repeatedly)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_user_table)
        await conn.run_sync(_migrate_chat_columns)
        await conn.run_sync(_migrate_homework_thread)


def _migrate_homework_thread(conn) -> None:
    """Add the forum-thread link to old homework rows (safe, idempotent)."""
    import sqlalchemy as sa

    inspector = sa.inspect(conn)
    if "homeworks" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("homeworks")}
    if "thread_id" not in existing:
        conn.execute(sa.text("ALTER TABLE homeworks ADD COLUMN thread_id INTEGER"))


def _migrate_chat_columns(conn) -> None:
    """Add columns introduced after the first release (forum topics, tests).

    SQLite cannot ALTER a column in place, but adding new ones is safe and
    idempotent: a column that already exists is skipped.
    """
    import sqlalchemy as sa

    inspector = sa.inspect(conn)
    if "chats" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("chats")}
    wanted = {
        "is_forum": "BOOLEAN",
        "topic_general": "INTEGER",
        "topic_homework": "INTEGER",
        "topic_test": "INTEGER",
        "topic_announcements": "INTEGER",
        "test_weekday": "INTEGER",
        "test_time": "VARCHAR(5)",
        "test_count": "INTEGER",
        "test_duration": "INTEGER",
        "last_test_at": "DATETIME",
    }
    changed = False
    for name, kind in wanted.items():
        if name not in existing:
            conn.execute(sa.text(f"ALTER TABLE chats ADD COLUMN {name} {kind}"))
            changed = True
    if changed:
        for name in ("test_count", "test_duration"):
            conn.execute(
                sa.text(f"UPDATE chats SET {name} = 0 WHERE {name} IS NULL")
            )
        conn.execute(sa.text("UPDATE chats SET test_count = 10 WHERE test_count = 0"))
        conn.execute(sa.text("UPDATE chats SET test_duration = 30 WHERE test_duration = 0"))


def _migrate_user_table(conn) -> None:
    """One-time upgrade for databases created before multi-group support.

    The old ``users`` table used the Telegram id as the primary key, so one
    row per person per group was impossible when they joined a second group.
    The old primary key value becomes ``tg_id``; every existing row (roles,
    names, notes, guardian contacts) is carried over into the new schema
    with a surrogate ``id``.
    """
    import sqlalchemy as sa

    inspector = sa.inspect(conn)
    if "users" not in inspector.get_table_names():
        return
    old_info = {col["name"]: col for col in inspector.get_columns("users")}
    if "tg_id" in old_info:
        return  # already on the multi-group schema

    # 1) old table: the primary key WAS the Telegram id → move it into tg_id.
    conn.execute(sa.text("ALTER TABLE users RENAME TO users_old"))
    Base.metadata.tables["users"].create(conn)

    def _copy_value(name: str) -> str:
        """NULL-safe value: the new columns are NOT NULL, old rows may be NULL."""
        kind = str(old_info[name].get("type", "")).upper()
        if "BOOL" in kind:
            return f"COALESCE({name}, 1)"
        if kind.startswith(("INT", "BIGINT")):
            return f"COALESCE({name}, 0)"
        if "DATETIME" in kind or "DATE" in kind:
            return f"COALESCE({name}, CURRENT_TIMESTAMP)"
        return f"COALESCE({name}, '')"

    keep = sorted(name for name in old_info if name != "id")
    selects = ", ".join(_copy_value(name) for name in keep)
    conn.execute(sa.text(
        f"INSERT INTO users (tg_id, {', '.join(keep)}) SELECT id, {selects} FROM users_old"
    ))
    conn.execute(sa.text("DROP TABLE users_old"))
    # 2) the explicit teacher-assignment table may also be missing.
    if "group_teachers" not in sa.inspect(conn).get_table_names():
        Base.metadata.tables["group_teachers"].create(conn)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Transactional session: commits on success, rolls back on error."""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose() -> None:
    await engine.dispose()
