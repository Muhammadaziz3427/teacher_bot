"""Points, penalties and the late-submission rules."""
from __future__ import annotations

from app.config import settings
from app.services.scoring import (
    KIND_HW_DONE,
    KIND_HW_LATE,
    KIND_HW_PARTIAL,
    KIND_HW_WRONG,
    points_for,
)

RULES = settings.points


def test_full_points_for_correct_work():
    points, kind = points_for(92, "correct", False)
    assert (points, kind) == (RULES.full, KIND_HW_DONE)


def test_partial_points_for_half_done_work():
    points, kind = points_for(60, "partial", False)
    assert (points, kind) == (RULES.partial, KIND_HW_PARTIAL)


def test_no_points_for_wrong_work():
    points, kind = points_for(20, "wrong", False)
    assert (points, kind) == (RULES.wrong, KIND_HW_WRONG)


def test_verdict_wins_over_a_low_score():
    # the AI said "correct" — trust it (the score band was reconciled already)
    points, kind = points_for(10, "correct", False)
    assert (points, kind) == (RULES.full, KIND_HW_DONE)


def test_late_work_is_halved_and_penalised():
    points, kind = points_for(92, "correct", True)
    base = RULES.full / 2 if RULES.late_halves_score else RULES.full
    assert round(points, 2) == round(base + RULES.late, 2)
    assert kind == KIND_HW_LATE


def test_score_thresholds_agree_with_the_prompt():
    # SYSTEM_PROMPT says: correct = 80-100, partial = 50-79, wrong = 0-49
    assert points_for(80, "correct", False)[1] == KIND_HW_DONE
    assert points_for(79, "partial", False)[1] == KIND_HW_PARTIAL
    assert points_for(50, "partial", False)[1] == KIND_HW_PARTIAL
    assert points_for(49, "wrong", False)[1] == KIND_HW_WRONG


def test_points_are_never_subunit():
    for score in (0, 33, 50, 79, 80, 100):
        for late in (False, True):
            points, _ = points_for(score, "partial", late)
            assert points == round(points, 2)