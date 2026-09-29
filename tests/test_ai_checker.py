"""AI output normalisation, JSON extraction and retry classification."""
from __future__ import annotations

from app import ai_checker
from app.ai_checker import CheckResult, _auth_error, _fallback, _normalise, _retryable, extract_json


# --- JSON extraction ------------------------------------------------------
def test_extract_json_plain():
    assert extract_json('{"score": 10}') == {"score": 10}


def test_extract_json_from_markdown_fence():
    assert extract_json('```json\n{"score": 20}\n```') == {"score": 20}


def test_extract_json_with_prose_around():
    assert extract_json('Sure! Here it is: {"score": 30} — done') == {"score": 30}


def test_extract_json_gives_up_cleanly():
    assert extract_json("no json at all") is None
    assert extract_json("") is None
    assert extract_json("[1, 2, 3]") is None       # a list is not an object


# --- retry classification -------------------------------------------------
class _Err(Exception):
    def __init__(self, status: int | None):
        super().__init__("boom")
        if status is not None:
            self.status_code = status


def test_transient_errors_are_retryable():
    assert _retryable(_Err(429)) is True
    assert _retryable(_Err(500)) is True
    assert _retryable(_Err(503)) is True
    assert _retryable(_Err(None)) is True          # timeouts / connection reset


def test_permanent_errors_are_not_retryable():
    assert _retryable(_Err(400)) is False
    assert _retryable(_Err(404)) is False


def test_auth_errors_are_recognised():
    assert _auth_error(_Err(401)) is True
    assert _auth_error(_Err(403)) is True
    assert _auth_error(_Err(429)) is False
    assert _auth_error(_Err(None)) is False


# --- score ↔ verdict reconciliation --------------------------------------
def test_low_score_lifted_into_partial_band():
    result = _normalise({"score": 1, "verdict": "partial"})
    assert result.score == 50 and result.verdict == "partial" and result.grade == "D"


def test_correct_verdict_keeps_a_top_score():
    assert _normalise({"score": 97, "verdict": "correct"}).score == 97


def test_wrong_verdict_never_shows_a_top_score():
    assert _normalise({"score": 97, "verdict": "wrong"}).score == 49


def test_unclear_forces_zero():
    result = _normalise({"score": 65, "verdict": "unclear"})
    assert result.score == 0 and result.verdict == "unclear"


def test_missing_verdict_is_derived_from_score():
    assert _normalise({"score": 92}).verdict == "correct"
    assert _normalise({"score": 55}).verdict == "partial"
    assert _normalise({"score": 10}).verdict == "wrong"


def test_score_is_clamped_to_0_100():
    assert _normalise({"score": 250, "verdict": "correct"}).score == 100
    assert _normalise({"score": -5, "verdict": "wrong"}).score == 0


# --- mistakes and tasks ---------------------------------------------------
def test_major_mistakes_come_first():
    result = _normalise({"score": 60, "verdict": "partial", "mistakes": [
        {"original": "alot", "correction": "a lot", "severity": "minor",
         "explanation": "two words"},
        {"original": "He go", "correction": "He goes", "severity": "major",
         "explanation": "3rd person"},
    ]})
    assert [m["severity"] for m in result.mistakes] == ["major", "minor"]


def test_unknown_severity_defaults_to_major():
    result = _normalise({"score": 60, "verdict": "partial", "mistakes": [
        {"original": "x", "correction": "y", "explanation": "z"},
    ]})
    assert result.mistakes[0]["severity"] == "major"


def test_empty_mistakes_are_dropped():
    result = _normalise({"score": 60, "verdict": "partial", "mistakes": [{"rule": "x"}]})
    assert result.mistakes == []


def test_task_statuses_use_a_known_vocabulary():
    result = _normalise({"score": 60, "verdict": "partial", "task_results": [
        {"task": "1", "status": "ok"},
        {"task": "2", "status": "NOT DONE"},
        {"task": "3", "status": "???"},
    ]})
    assert [row["status"] for row in result.tasks] == ["correct", "missing", "partial"]


def test_result_status_property():
    assert CheckResult(ok=True).status == "checked"
    assert CheckResult(ok=False).status == "pending"


# --- offline fallback -----------------------------------------------------
def test_fallback_helps_even_without_ai():
    result = _fallback("i alot dont know", "uz", "test reason")
    assert result.ok is False and result.status == "pending"
    categories = {m["category"] for m in result.mistakes}
    assert {"spelling", "punctuation"} & categories
    assert result.error == "test reason"