"""SQLAlchemy ORM models for the English teacher bot."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Chat(Base):
    """A Telegram group that holds one class.

    In forum (topic-based) groups every message carries a ``message_thread_id``
    — the topic it was posted in. The teacher never has to look up those ids:
    the first time a command is used inside a topic the bot remembers that
    topic as the place where this kind of message belongs (auto-detection).
    """

    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    subject: Mapped[str] = mapped_column(String(64), default="English")
    level: Mapped[str] = mapped_column(String(32), default="")
    language: Mapped[str] = mapped_column(String(4), default="bi")  # uz|en|bi
    default_due_hours: Mapped[int] = mapped_column(Integer, default=24)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # --- forum topics (0/NULL = not detected yet → post to General) -----
    is_forum: Mapped[bool] = mapped_column(Boolean, default=False)
    topic_general: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    topic_homework: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    topic_test: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    topic_announcements: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # --- weekly test schedule (auto-posting, no teacher needed) --------
    test_weekday: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 0=Mon
    test_time: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)   # "14:00"
    test_count: Mapped[int] = mapped_column(Integer, default=10)
    test_duration: Mapped[int] = mapped_column(Integer, default=30)  # minutes
    last_test_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Test(Base):
    """A quiz that the bot posts into the group's Test topic."""

    __tablename__ = "tests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    lesson_topics: Mapped[str] = mapped_column(String(500), default="")
    source: Mapped[str] = mapped_column(String(16), default="manual")  # manual|ai
    thread_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, index=True)
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    # draft | scheduled | running | finished
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30)
    created_by: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class TestQuestion(Base):
    """One multiple-choice question; exactly one correct option."""

    __tablename__ = "test_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    test_id: Mapped[int] = mapped_column(ForeignKey("tests.id", ondelete="CASCADE"),
                                          index=True)
    position: Mapped[int] = mapped_column(Integer, default=1)
    text: Mapped[str] = mapped_column(Text, default="")
    options: Mapped[list[str]] = mapped_column(JSON, default=list)   # 4 choices
    correct: Mapped[int] = mapped_column(Integer, default=0)          # 0..3
    explanation: Mapped[str] = mapped_column(String(500), default="")
    message_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class TestAnswer(Base):
    """One student's answer to one question (unique per question)."""

    __tablename__ = "test_answers"
    __table_args__ = (UniqueConstraint("question_id", "student_id", name="uq_answer"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    test_id: Mapped[int] = mapped_column(Integer, index=True)
    question_id: Mapped[int] = mapped_column(Integer, index=True)
    student_id: Mapped[int] = mapped_column(BigInteger, index=True)  # Telegram id
    choice: Mapped[int] = mapped_column(Integer, default=0)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class User(Base):
    """One membership row: a Telegram user inside one class group.

    The primary key is the surrogate ``id``; the pair ``(chat_id, tg_id)``
    identifies a person inside one group, so the same student or teacher can
    belong to many groups without the rows clobbering each other.
    Everywhere else in the database (submissions, attendance, point events)
    people are referenced by their Telegram id (``tg_id``) scoped by chat.
    """

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("chat_id", "tg_id", name="uq_user_chat"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    role: Mapped[str] = mapped_column(String(16), default="student")  # student|teacher|admin
    level: Mapped[str] = mapped_column(String(16), default="")        # CEFR: A1..C2
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    guardian_contact: Mapped[str] = mapped_column(String(120), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class GroupTeacher(Base):
    """Explicit teacher ↔ group assignment (for learning centers).

    Teachers listed here can open the group in their private dashboard even
    when they were never auto-registered from inside the group chat.
    Global admins and ``TEACHER_IDS`` from the config always have access too.
    """

    __tablename__ = "group_teachers"
    __table_args__ = (UniqueConstraint("chat_id", "tg_id", name="uq_group_teacher"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, index=True)
    assigned_by: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class LessonSlot(Base):
    """Weekly timetable entry — used to compute the 'next lesson' deadline."""

    __tablename__ = "lesson_slots"
    __table_args__ = (UniqueConstraint("chat_id", "weekday", "start_time", name="uq_slot"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    weekday: Mapped[int] = mapped_column(Integer)          # 0=Monday ... 6=Sunday
    start_time: Mapped[str] = mapped_column(String(5))     # "14:30"
    subject: Mapped[str] = mapped_column(String(64), default="English")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Homework(Base):
    """An assignment given by the teacher."""

    __tablename__ = "homeworks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    topic: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    criteria: Mapped[str] = mapped_column(Text, default="")     # rubric / skill focus
    skill: Mapped[str] = mapped_column(String(64), default="")   # grammar|vocabulary|writing|reading
    media_file_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    media_type: Mapped[str] = mapped_column(String(16), default="")
    message_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    thread_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    due_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active|closed
    created_by: Mapped[int] = mapped_column(BigInteger, default=0)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reminders_sent: Mapped[list[int]] = mapped_column(JSON, default=list)


class Submission(Base):
    """A student's answer to a homework (text and/or photo)."""

    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("homework_id", "student_id", name="uq_submission"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    homework_id: Mapped[int] = mapped_column(
        ForeignKey("homeworks.id", ondelete="CASCADE"), index=True
    )
    student_id: Mapped[int] = mapped_column(BigInteger, index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    content: Mapped[str] = mapped_column(Text, default="")
    media_file_id: Mapped[Optional[str]] = mapped_column(String(220), nullable=True)
    media_type: Mapped[str] = mapped_column(String(16), default="")  # photo|document|text
    message_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    is_late: Mapped[bool] = mapped_column(Boolean, default=False)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    # pending | checked | manual | failed
    ai_score: Mapped[int] = mapped_column(Integer, default=0)
    ai_grade: Mapped[str] = mapped_column(String(4), default="")
    ai_verdict: Mapped[str] = mapped_column(String(16), default="")
    ai_summary: Mapped[str] = mapped_column(Text, default="")
    ai_mistakes: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    ai_tasks: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    ai_topics: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    ai_strengths: Mapped[list[str]] = mapped_column(JSON, default=list)
    ai_tips: Mapped[list[str]] = mapped_column(JSON, default=list)
    ai_level: Mapped[str] = mapped_column(String(8), default="")
    ai_raw: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    teacher_comment: Mapped[str] = mapped_column(Text, default="")
    graded_by: Mapped[int] = mapped_column(BigInteger, default=0)
    points_awarded: Mapped[float] = mapped_column(Float, default=0.0)


class Attendance(Base):
    """Daily attendance of a student for a class day."""

    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("chat_id", "student_id", "day", name="uq_attendance"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    student_id: Mapped[int] = mapped_column(BigInteger, index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(16), default="present")
    # present | late | absent | excused
    note: Mapped[str] = mapped_column(String(255), default="")
    marked_by: Mapped[int] = mapped_column(BigInteger, default=0)
    marked_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PointEvent(Base):
    """Every point / penalty ever awarded — the ledger behind all reports."""

    __tablename__ = "point_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    student_id: Mapped[int] = mapped_column(BigInteger, index=True)
    kind: Mapped[str] = mapped_column(String(24), default="manual")
    points: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(String(400), default="")
    homework_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    event_key: Mapped[Optional[str]] = mapped_column(String(96), unique=True, nullable=True)
    created_by: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class Report(Base):
    """A generated report kept for history / re-sending."""

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    student_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    period: Mapped[str] = mapped_column(String(16), default="weekly")
    start: Mapped[date] = mapped_column(Date)
    end: Mapped[date] = mapped_column(Date)
    text: Mapped[str] = mapped_column(Text, default="")
    file_path: Mapped[str] = mapped_column(String(255), default="")
    created_by: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
