"""Logging: console + rotating file, configured exactly once.

``logs/bot.log`` keeps the last ~8 MB (4 files) — enough to answer "what
happened last night?" after the bot has been restarted. Every AI call logs
its latency and token usage, every retry and every failed job logs why.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"


def setup_logging(level: int = logging.INFO, log_dir: Path | None = None) -> Path:
    """Attach a console handler (if none) and a rotating file handler.

    Safe to call more than once — the second call is a no-op. Returns the
    log file that is being written.
    """
    root = logging.getLogger()
    if getattr(root, "_teacher_bot_configured", False):
        return (log_dir or LOG_DIR) / "bot.log"
    root.setLevel(level)

    formatter = logging.Formatter(FORMAT)
    if not root.handlers:                     # nothing configured yet
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(formatter)
        root.addHandler(console)

    directory = log_dir or LOG_DIR
    directory.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        directory / "bot.log",
        maxBytes=2_000_000,                   # 2 MB × 4 files ≈ 8 MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    root._teacher_bot_configured = True       # type: ignore[attr-defined]
    return directory / "bot.log"