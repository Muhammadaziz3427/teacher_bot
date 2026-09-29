"""Handler registration helper."""

from __future__ import annotations

from aiogram import Dispatcher

from . import common, reports, student, teacher, tests


def register_handlers(dp: Dispatcher) -> None:
    """Router order matters: commands first, the catch-all submission last."""
    dp.include_router(common.router)
    dp.include_router(teacher.router)
    dp.include_router(tests.router)
    dp.include_router(reports.router)
    dp.include_router(student.router)
