"""Application configuration loaded from environment / .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _str(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return value.strip() if value is not None and value.strip() else default


def _int(name: str, default: int) -> int:
    try:
        return int(float(_str(name, str(default)) or default))
    except (TypeError, ValueError):
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(_str(name, str(default)) or default)
    except (TypeError, ValueError):
        return default


def _bool(name: str, default: bool = False) -> bool:
    raw = _str(name, "true" if default else "false").lower()
    return raw in {"1", "true", "yes", "y", "on"}


def _ids(name: str) -> frozenset[int]:
    raw = _str(name).replace(";", ",").replace(" ", ",")
    out: set[int] = set()
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            out.add(int(chunk))
        except ValueError:
            continue
    return frozenset(out)


def _ints(name: str, default: tuple[int, ...]) -> tuple[int, ...]:
    raw = _str(name)
    if not raw:
        return default
    values: list[int] = []
    for chunk in raw.replace(";", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            values.append(int(float(chunk)))
        except ValueError:
            continue
    return tuple(values) or default


@dataclass(frozen=True, slots=True)
class PointsRules:
    """Everything a teacher can tune about the grading/penalty system."""

    full: float          # correct homework
    partial: float       # homework with minor mistakes
    wrong: float         # homework submitted but wrong
    late: float          # penalty for submitting after the deadline (negative)
    missing: float       # penalty for not submitting at all (negative)
    absent: float        # penalty for missing a lesson (negative)
    attendance_late: float  # penalty for being late to a lesson (negative)
    late_halves_score: bool  # a late submission only earns half of the points


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    admin_ids: frozenset[int]
    teacher_ids: frozenset[int]
    allowed_chat_types: frozenset[str]

    openai_api_key: str
    openai_base_url: str
    ai_model: str
    ai_vision_model: str
    ai_temperature: float
    ai_max_tokens: int
    ai_timeout: int
    ai_enabled: bool

    tz_name: str
    db_file: str
    exports_dir: str
    subject: str
    target_language: str
    default_due_hours: int
    reminder_hours: tuple[int, ...]
    auto_weekly_report: bool
    auto_weekly_day: str
    auto_weekly_hour: int
    points: PointsRules

    # --- Blok 4: voice, confirmation, deep links, mini app ---------------
    bot_username: str
    confirm_submissions: bool
    stt_model: str
    stt_api_key: str
    stt_base_url: str
    miniapp_enabled: bool
    miniapp_host: str
    miniapp_port: int
    miniapp_token: str
    miniapp_public_url: str

    # --- derived -----------------------------------------------------
    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.tz_name)

    @property
    def db_path(self) -> Path:
        path = Path(self.db_file)
        return path if path.is_absolute() else BASE_DIR / path

    @property
    def db_url(self) -> str:
        path = self.db_path
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite+aiosqlite:///{path.as_posix()}"

    @property
    def exports_path(self) -> Path:
        path = Path(self.exports_dir)
        return path if path.is_absolute() else BASE_DIR / path

    @property
    def ai_ready(self) -> bool:
        return bool(self.ai_enabled and self.openai_api_key)

    @property
    def stt_ready(self) -> bool:
        """Voice notes need a transcription key (falls back to the AI key)."""
        return bool(self.stt_api_key or self.openai_api_key)

    @property
    def stt_endpoint(self) -> str:
        """Where transcription runs: its own URL, else the main provider's.

        OpenRouter exposes ``/audio/transcriptions`` on the same base URL, so
        one key can serve both checks and voice notes once the account has the
        minimum audio balance.
        """
        return self.stt_base_url or self.openai_base_url

    @property
    def miniapp_ready(self) -> bool:
        return bool(self.miniapp_enabled and self.miniapp_token)

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids

    def is_teacher(self, user_id: int) -> bool:
        return user_id in self.admin_ids or user_id in self.teacher_ids


def build_settings() -> Settings:
    return Settings(
        bot_token=_str("BOT_TOKEN"),
        admin_ids=_ids("ADMIN_IDS"),
        teacher_ids=_ids("TEACHER_IDS"),
        allowed_chat_types=frozenset(
            t.strip()
            for t in _str("BOT_ALLOWED_CHAT_TYPES", "group,supergroup").split(",")
            if t.strip()
        ),
        openai_api_key=_str("OPENAI_API_KEY"),
        openai_base_url=_str("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        ai_model=_str("AI_MODEL", "gpt-4o-mini"),
        ai_vision_model=_str("AI_VISION_MODEL", "gpt-4o-mini"),
        ai_temperature=_float("AI_TEMPERATURE", 0.2),
        ai_max_tokens=_int("AI_MAX_TOKENS", 1600),
        ai_timeout=_int("AI_REQUEST_TIMEOUT", 90),
        ai_enabled=_bool("AI_ENABLED", True),
        tz_name=_str("TZ", "Asia/Tashkent"),
        db_file=_str("DB_FILE", "data/teacher_bot.db"),
        exports_dir=_str("EXPORTS_DIR", "data/exports"),
        subject=_str("DEFAULT_SUBJECT", "English"),
        target_language=_str("TARGET_LANGUAGE", "English"),
        default_due_hours=_int("DEFAULT_DUE_HOURS", 24),
        reminder_hours=_ints("REMINDER_HOURS", (24, 1)),
        auto_weekly_report=_bool("AUTO_WEEKLY_REPORT", True),
        auto_weekly_day=_str("AUTO_WEEKLY_DAY", "sun"),
        auto_weekly_hour=_int("AUTO_WEEKLY_HOUR", 20),
        points=PointsRules(
            full=_float("POINT_FULL", 2.0),
            partial=_float("POINT_PARTIAL", 1.0),
            wrong=_float("POINT_WRONG", 0.0),
            late=_float("POINT_LATE", -1.0),
            missing=_float("POINT_MISSING", -3.0),
            absent=_float("POINT_ABSENT", -1.0),
            attendance_late=_float("POINT_LATE_ATTENDANCE", -0.5),
            late_halves_score=_bool("LATE_HALVES_SCORE", True),
        ),
        bot_username=_str("BOT_USERNAME").lstrip("@"),
        confirm_submissions=_bool("CONFIRM_SUBMISSIONS", False),
        stt_model=_str("STT_MODEL", "whisper-1"),
        stt_api_key=_str("STT_API_KEY"),
        stt_base_url=_str("STT_BASE_URL").rstrip("/"),
        miniapp_enabled=_bool("MINIAPP_ENABLED", False),
        miniapp_host=_str("MINIAPP_HOST", "127.0.0.1"),
        miniapp_port=_int("MINIAPP_PORT", 8080),
        miniapp_token=_str("MINIAPP_TOKEN"),
        miniapp_public_url=_str("MINIAPP_PUBLIC_URL").rstrip("/"),
    )


settings = build_settings()
