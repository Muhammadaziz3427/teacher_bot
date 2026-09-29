"""FSM states used by the guided flows."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class HomeworkWizard(StatesGroup):
    title = State()
    skill = State()
    description = State()
    due = State()
    media = State()
    confirm = State()


class ManualGrade(StatesGroup):
    score = State()


class ExtraTaskWizard(StatesGroup):
    task = State()


class StudentSubmit(StatesGroup):
    content = State()


class TestWizard(StatesGroup):
    manual = State()
