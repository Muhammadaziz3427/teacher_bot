"""Inline keyboards for every flow."""

from __future__ import annotations

from typing import Iterable, Sequence

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .i18n import attendance_status_label, skill_label, t
from .models import Chat, Homework, User
from .utils import fmt_date_short

SKILLS = ("grammar", "vocabulary", "writing", "reading", "listening", "mixed")


def skills_kb(lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for skill in SKILLS:
        builder.button(text=skill_label(skill, lang), callback_data=f"wiz:skill:{skill}")
    builder.adjust(2, 2, 2)
    return builder.as_markup()


def media_kb(lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("btn_skip", lang), callback_data="wiz:skip")
    builder.button(text=t("btn_cancel", lang), callback_data="wiz:cancel")
    builder.adjust(1)
    return builder.as_markup()


def wizard_confirm_kb(lang: str) -> InlineKeyboardMarkup:
    """Confirmation inside the homework-creation wizard."""
    builder = InlineKeyboardBuilder()
    builder.button(text=t("btn_confirm", lang), callback_data="wiz:confirm")
    builder.button(text=t("btn_cancel", lang), callback_data="wiz:cancel")
    builder.adjust(1)
    return builder.as_markup()


confirm_kb = wizard_confirm_kb      # old name kept for compatibility


def homework_list_kb(homeworks: Sequence[Homework], lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for homework in homeworks:
        builder.button(
            text=f"#{homework.id} {homework.title[:28]}",
            callback_data=f"hw:view:{homework.id}",
        )
        builder.button(text=t("btn_close", lang), callback_data=f"hw:close:{homework.id}")
        builder.button(text=t("btn_remind", lang), callback_data=f"hw:remind:{homework.id}")
        builder.button(text=t("btn_stats", lang), callback_data=f"hw:stats:{homework.id}")
        builder.adjust(*([1, 3] * len(homeworks)))
    return builder.as_markup()


def homework_actions_kb(homework_id: int, lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("btn_remind", lang), callback_data=f"hw:remind:{homework_id}")
    builder.button(text=t("btn_stats", lang), callback_data=f"hw:stats:{homework_id}")
    builder.button(text=t("btn_close", lang), callback_data=f"hw:close:{homework_id}")
    builder.adjust(2, 1)
    return builder.as_markup()


def attendance_kb(
    students: Sequence[User], marks: dict[int, str], lang: str, chat_id: int = 0
) -> InlineKeyboardMarkup:
    """Attendance grid; `chat_id` keeps the mark inside the right group when the
    board is opened from the private dashboard (0 = use the current chat)."""
    builder = InlineKeyboardBuilder()
    for student in students:
        status = marks.get(student.tg_id)
        icon = {"present": "✅", "late": "⏰", "absent": "❌", "excused": "🟡"}.get(status, "⬜")
        builder.button(
            text=f"{icon} {student.full_name[:26]}",
            callback_data=f"att:cycle:{chat_id}:{student.tg_id}",
        )
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(text=t("att_all_present", lang),
                             callback_data=f"att:all:{chat_id}:0"),
        InlineKeyboardButton(text=t("att_done", lang), callback_data=f"att:done:{chat_id}:0"),
    )
    return builder.as_markup()


def feedback_review_kb(submission_id: int, lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("btn_accept", lang), callback_data=f"sub:accept:{submission_id}")
    builder.button(text=t("btn_partial", lang), callback_data=f"sub:partial:{submission_id}")
    builder.button(text=t("btn_reject", lang), callback_data=f"sub:reject:{submission_id}")
    builder.adjust(1)
    return builder.as_markup()


def pending_kb(submission_ids: Iterable[int], lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for submission_id in submission_ids:
        builder.button(
            text=f"✍️ #{submission_id}", callback_data=f"sub:grade:{submission_id}"
        )
    builder.adjust(4)
    return builder.as_markup()


def students_kb(
    students: Sequence[User],
    prefix: str,
    lang: str,
    period: str = "weekly",
    columns: int = 2,
    chat_id: int = 0,
) -> InlineKeyboardMarkup:
    """One button per student. `chat_id` is carried so the button still works
    when the report was delivered to a teacher's private chat."""
    builder = InlineKeyboardBuilder()
    for student in students:
        builder.button(
            text=student.full_name[:28],
            callback_data=f"{prefix}:{chat_id}:{period}:{student.tg_id}",
        )
    builder.adjust(columns)
    return builder.as_markup()


def report_kb(chat_id: int, target_id: int, period: str, lang: str) -> InlineKeyboardMarkup:
    """Buttons under a report: switch period, export, pick another student."""
    builder = InlineKeyboardBuilder()
    for other, label in (("weekly", "7d"), ("monthly", "30d"), ("yearly", "1y")):
        mark = "• " if other == period else ""
        builder.button(
            text=f"{mark}{label}", callback_data=f"rep:period:{chat_id}:{other}:{target_id}"
        )
    builder.button(
        text=t("btn_export", lang),
        callback_data=f"rep:export:{chat_id}:{period}:{target_id}",
    )
    builder.button(
        text="👥", callback_data=f"rep:pick:{chat_id}:{period}:{target_id}"
    )
    builder.adjust(3, 1, 1)
    return builder.as_markup()


def groups_kb(chats: Sequence[Chat], lang: str) -> InlineKeyboardMarkup:
    """Teacher dashboard: one button per managed group."""
    builder = InlineKeyboardBuilder()
    for chat in chats:
        title = (chat.title or str(chat.id))[:30]
        builder.button(text=f"🏫 {title}", callback_data=f"dash:open:{chat.id}")
    builder.adjust(1)
    return builder.as_markup()


def sections_kb(chat_id: int, lang: str) -> InlineKeyboardMarkup:
    """Teacher dashboard: sections of one group."""
    builder = InlineKeyboardBuilder()
    builder.button(text=t("dash_btn_overview", lang), callback_data=f"dash:overview:{chat_id}")
    builder.button(text=t("dash_btn_attendance", lang), callback_data=f"dash:attendance:{chat_id}")
    builder.button(text=t("dash_btn_homeworks", lang), callback_data=f"dash:homeworks:{chat_id}")
    builder.button(text=t("dash_btn_students", lang), callback_data=f"dash:students:{chat_id}")
    builder.button(text=t("dash_btn_reports", lang), callback_data=f"dash:reports:{chat_id}")
    builder.button(text=t("dash_btn_settings", lang), callback_data=f"dash:settings:{chat_id}")
    builder.button(text=t("dash_back_groups", lang), callback_data="dash:groups:0")
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


def back_sections_kb(chat_id: int, lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("dash_back_sections", lang), callback_data=f"dash:open:{chat_id}")
    builder.adjust(1)
    return builder.as_markup()


def dash_periods_kb(chat_id: int, lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("dash_period_weekly", lang), callback_data=f"dash:repw:{chat_id}")
    builder.button(text=t("dash_period_monthly", lang), callback_data=f"dash:repm:{chat_id}")
    builder.button(text=t("dash_period_yearly", lang), callback_data=f"dash:repy:{chat_id}")
    builder.button(text=t("dash_btn_export", lang), callback_data=f"dash:xlsx:{chat_id}")
    builder.button(text=t("dash_back_sections", lang), callback_data=f"dash:open:{chat_id}")
    builder.adjust(3, 1, 1)
    return builder.as_markup()


def cancel_kb(lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("btn_cancel", lang), callback_data="wiz:cancel")
    builder.adjust(1)
    return builder.as_markup()


def due_kb(lang: str) -> InlineKeyboardMarkup:
    """Deadline step: use the next lesson, or cancel the wizard."""
    builder = InlineKeyboardBuilder()
    builder.button(text=t("btn_next_lesson", lang), callback_data="wiz:due_default")
    builder.button(text=t("btn_cancel", lang), callback_data="wiz:cancel")
    builder.adjust(1)
    return builder.as_markup()


def student_menu_kb(lang: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📚 /myhomework", callback_data="me:homework:0:0")
    builder.button(text="🏅 /mypoints", callback_data="me:points:0:0")
    builder.button(text="🗓 /myattendance", callback_data="me:attendance:0:0")
    builder.button(text="📊 /mystats", callback_data="me:stats:0:0")
    builder.adjust(1, 1)
    return builder.as_markup()


# --- Blok 4 --------------------------------------------------------------
def submission_confirm_kb(submission_id: int, lang: str) -> InlineKeyboardMarkup:
    """The student's own ✅/❌ for a submission that is not checked yet."""
    builder = InlineKeyboardBuilder()
    builder.button(text=t("btn_submitted", lang),
                   callback_data=f"sub:yes:{submission_id}")
    builder.button(text=t("btn_not_yet", lang),
                   callback_data=f"sub:no:{submission_id}")
    builder.adjust(1, 1)
    return builder.as_markup()


def parent_link_kb(url: str, lang: str) -> InlineKeyboardMarkup:
    """One tap for the parent: opens the bot and shows the report."""
    builder = InlineKeyboardBuilder()
    builder.button(text=t("btn_parent_link", lang), url=url)
    builder.adjust(1)
    return builder.as_markup()


def miniapp_kb(url: str, lang: str) -> InlineKeyboardMarkup:
    """Opens the teacher dashboard as a Telegram web app."""
    builder = InlineKeyboardBuilder()
    builder.button(text=t("btn_open_dashboard", lang), web_app=WebAppInfo(url=url))
    builder.adjust(1, 1)
    return builder.as_markup()
    return builder.as_markup()
