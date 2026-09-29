"""AI homework checker for English tasks — handles text and photo submissions."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Sequence

from .config import settings
from .i18n import category_label, grade_for

log = logging.getLogger(__name__)

CATEGORIES = (
    "grammar, tense, articles, prepositions, spelling, punctuation, word order, "
    "vocabulary, word form, pronoun, plural, capitalisation, translation, missing answer, other"
)

_LANGUAGE_RULES = {
    "en": "English",
    "uz": "Uzbek (o'zbek tili), but keep all English corrections in English",
    "bi": "Uzbek (o'zbek tili) as the explanation, written directly after the English "
          "correction, in the form 'EN | UZ'",
}

SYSTEM_PROMPT = """You are a strict but encouraging English teacher and examiner \
checking a school student's homework.

You receive:
1) The assignment the teacher gave (topic, skill, description, optional rubric).
2) The student's answer: written text and/or a photo of their notebook or workbook.

Your job: check ONLY against the given assignment, find EVERY real mistake, and \
explain it so that a school student understands it.

Rules:
- Corrections ("correction") must ALWAYS be in English — that is the language being learned.
- "explanation", "comment", "summary", "note", "tips" must be written in: {language}.
- Never invent content that is not in the student's work.
- If the photo is unreadable/blurry or the answer is empty, use verdict="unclear", \
score=0 and explain what the student should re-send.
- Score 0-100 based on how much of the task is done correctly (not handwriting quality).
- "score" must be an integer 0-100 AND must agree with "verdict": \
correct = 80-100, partial = 50-79, wrong = 0-49, unclear = 0.
- Put the most important mistakes first, maximum 12 items.
- "severity" is "major" when the mistake changes the answer (wrong grammar, \
wrong word, missing answer) and "minor" for spelling/punctuation/style only.
- In "original" copy the exact words the student wrote.
- Choose "category" only from this list: {categories}
- "rule" is a short English name of the grammar/vocabulary rule (e.g. "Present Simple: \
3rd person -s", "a/an before consonant", "comparative: -er/more").
- "tips" must be concrete practice actions (e.g. "Write 5 sentences with 'there is/are'").
- "task_results": one entry per exercise you can identify, status = correct|partial|wrong|missing.
- "strengths": up to 4 things the student did well.
- "estimated_level": CEFR estimate (A1, A2, B1, B2...).

Answer with ONE valid JSON object, nothing else, exactly this shape:
{{
  "score": 0,
  "verdict": "correct|partial|wrong|unclear",
  "summary": "",
  "task_results": [{{"task": "", "status": "correct", "comment": ""}}],
  "mistakes": [{{"original": "", "correction": "", "category": "",
                 "rule": "", "explanation": "", "severity": "major|minor"}}],
  "topics": [{{"topic": "", "level": "weak|ok|strong", "note": ""}}],
  "strengths": [""],
  "tips": [""],
  "estimated_level": "A2"
}}"""


@dataclass(slots=True)
class CheckResult:
    """Normalised AI verdict."""

    ok: bool = False
    score: int = 0
    grade: str = ""
    verdict: str = "unclear"
    summary: str = ""
    tasks: list[dict[str, Any]] = field(default_factory=list)
    mistakes: list[dict[str, Any]] = field(default_factory=list)
    topics: list[dict[str, Any]] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    tips: list[str] = field(default_factory=list)
    level: str = ""
    error: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def status(self) -> str:
        return "checked" if self.ok else "pending"


_CLIENT: Any = None


def _client():
    """Reuse one AsyncOpenAI client (and its connection pool) for every check."""
    global _CLIENT
    if _CLIENT is None:
        from openai import AsyncOpenAI

        _CLIENT = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=settings.ai_timeout,
        )
    return _CLIENT


def build_system_prompt(lang: str) -> str:
    return SYSTEM_PROMPT.format(language=_LANGUAGE_RULES.get(lang, _LANGUAGE_RULES["bi"]),
                                categories=CATEGORIES)


def build_user_content(
    homework: Any,
    student_text: str,
    images: Sequence[tuple[bytes, str]],
    lang: str,
) -> list[dict[str, Any]]:
    """Build the multimodal user message (text + optional images)."""
    parts: list[dict[str, Any]] = []
    lines = [
        "ASSIGNMENT:",
        f"- Lesson/topic: {getattr(homework, 'title', '') or '—'}",
        f"- Skill: {getattr(homework, 'skill', '') or 'general'}"
        f" ({category_label(getattr(homework, 'skill', ''), lang)})",
        f"- Task description: {getattr(homework, 'description', '') or '—'}",
    ]
    criteria = getattr(homework, "criteria", "")
    if criteria:
        lines.append(f"- Teacher's rubric: {criteria}")
    lines.append("")
    if student_text:
        lines.append("STUDENT'S WRITTEN ANSWER:")
        lines.append(student_text[:6000])
    else:
        lines.append("STUDENT'S WRITTEN ANSWER: (none — see the photo(s) below)")
    if images:
        lines.append("")
        lines.append(f"{len(images)} photo(s) of the student's work are attached.")
    parts.append({"type": "text", "text": "\n".join(lines)})

    for blob, mime in images:
        encoded = base64.b64encode(blob).decode("ascii")
        parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime or 'image/jpeg'};base64,{encoded}"},
        })
    return parts


async def check_submission(
    homework: Any,
    student_text: str,
    images: Sequence[tuple[bytes, str]] = (),
    lang: str = "bi",
) -> CheckResult:
    """Send the submission to the AI and return a normalised verdict."""
    if not settings.ai_ready:
        return _fallback(student_text, lang, "AI is not configured")

    model = settings.ai_vision_model if images else settings.ai_model
    messages = [
        {"role": "system", "content": build_system_prompt(lang)},
        {"role": "user", "content": build_user_content(homework, student_text, images, lang)},
    ]
    try:
        client = _client()
        payload = await _request(client, model, messages)
    except Exception as exc:  # network, auth, quota, bad JSON …
        return _fallback(student_text, lang, f"{type(exc).__name__}: {exc}"[:400])
    return _normalise(payload)


RETRY_DELAYS = (1.0, 3.0)  # seconds between attempts → 3 calls in total


def _retryable(exc: Exception) -> bool:
    """Retry only errors that may disappear on their own (429/5xx/network).

    Auth / bad-request problems are permanent — retrying them would only waste
    the student's time, so they fall through to the offline fallback at once.
    """
    status = getattr(exc, "status_code", None)
    if status is None:  # timeout, DNS, connection reset …
        return True
    return int(status) in {408, 409, 429} or int(status) >= 500


def _auth_error(exc: Exception) -> bool:
    """Wrong/expired key or missing permission — retrying cannot fix it."""
    return int(getattr(exc, "status_code", 0) or 0) in {401, 403}


async def _request(client: Any, model: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Call the chat completions endpoint, retrying transient failures.

    Order of attempts: JSON mode → plain mode (some providers reject
    ``response_format``) → retry from the top after a short backoff.
    """
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": settings.ai_temperature,
        "max_tokens": settings.ai_max_tokens,
    }
    last_error: Exception = ValueError("AI did not return valid JSON")
    for attempt in range(1 + len(RETRY_DELAYS)):
        if attempt:
            await asyncio.sleep(RETRY_DELAYS[attempt - 1])
        started = time.monotonic()
        try:
            try:
                response = await client.chat.completions.create(
                    response_format={"type": "json_object"}, **kwargs
                )
            except Exception as exc:
                if _retryable(exc) or _auth_error(exc):
                    raise  # transient / auth → handled by the outer handler
                response = await client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content if response.choices else ""
            payload = extract_json(content or "")
            if payload is not None:
                _log_usage(model, response, time.monotonic() - started, attempt)
                return payload
            last_error = ValueError("AI did not return valid JSON")
        except Exception as exc:
            if not _retryable(exc):
                raise
            log.warning("AI attempt %d failed (%s): %s",
                        attempt + 1, type(exc).__name__, str(exc)[:200])
            last_error = exc
    raise last_error


def _log_usage(model: str, response: Any, seconds: float, attempt: int) -> None:
    """One INFO line per check — latency + tokens for /check and log files."""
    usage = getattr(response, "usage", None)
    log.info("AI ok model=%s %.1fs prompt=%s completion=%s attempt=%d",
             model, seconds,
             getattr(usage, "prompt_tokens", "?"),
             getattr(usage, "completion_tokens", "?"),
             attempt + 1)


def extract_json(content: str) -> dict[str, Any] | None:
    """Pull a JSON object out of the model's reply (markdown fences included)."""
    text = (content or "").strip()
    if not text:
        return None
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, "", {}):
        return []
    return [value]


def _as_str_list(value: Any) -> list[str]:
    out: list[str] = []
    for item in _as_list(value):
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        elif isinstance(item, dict):
            text = item.get("text") or item.get("comment") or item.get("note")
            if text:
                out.append(str(text).strip())
    return out


def _as_dict_list(value: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in _as_list(value):
        if isinstance(item, dict):
            out.append({k: v for k, v in item.items() if v is not None})
        elif isinstance(item, str) and item.strip():
            out.append({"comment": item.strip()})
    return out


def _normalise(payload: dict[str, Any]) -> CheckResult:
    """Clamp and clean the AI's JSON so the rest of the code can trust it."""
    try:
        score = int(round(float(payload.get("score", 0) or 0)))
    except (TypeError, ValueError):
        score = 0
    score = max(0, min(100, score))

    verdict = str(payload.get("verdict", "") or "").strip().lower()
    if verdict not in {"correct", "partial", "wrong", "unclear"}:
        verdict = "correct" if score >= 80 else "partial" if score >= 50 else "wrong"
    score, verdict = _reconcile(score, verdict)

    clean_mistakes: list[dict[str, Any]] = []
    for item in _as_dict_list(payload.get("mistakes"))[:12]:
        original = str(item.get("original", "") or "").strip()
        correction = str(item.get("correction", "") or "").strip()
        explanation = str(item.get("explanation") or item.get("comment") or "").strip()
        if not (original or correction or explanation):
            continue
        severity = str(item.get("severity", "") or "").strip().lower()
        clean_mistakes.append({
            "original": original,
            "correction": correction,
            "category": str(item.get("category", "") or "other").strip().lower(),
            "rule": str(item.get("rule", "") or "").strip(),
            "explanation": explanation,
            "severity": severity if severity in {"major", "minor"} else "major",
        })
    # the most damaging mistakes must be read first (stable sort keeps AI order)
    clean_mistakes.sort(key=lambda m: 0 if m["severity"] == "major" else 1)

    return CheckResult(
        ok=True,
        score=score,
        grade=grade_for(score),
        verdict=verdict,
        summary=str(payload.get("summary", "") or "").strip(),
        tasks=_clean_tasks(payload.get("task_results")),
        mistakes=clean_mistakes,
        topics=_as_dict_list(payload.get("topics"))[:10],
        strengths=_as_str_list(payload.get("strengths"))[:5],
        tips=_as_str_list(payload.get("tips"))[:5],
        level=str(payload.get("estimated_level", "") or "").strip()[:8],
        raw=payload,
    )


# verdict → the score band it must agree with (see SYSTEM_PROMPT)
VERDICT_BANDS: dict[str, tuple[int, int]] = {
    "correct": (80, 100),
    "partial": (50, 79),
    "wrong": (0, 49),
}

_TASK_STATUSES = {"correct", "partial", "wrong", "missing"}
_TASK_ALIASES = {
    "ok": "correct", "right": "correct", "yes": "correct", "true": "correct",
    "good": "correct", "solved": "correct",
    "bad": "wrong", "incorrect": "wrong", "no": "wrong", "false": "wrong",
    "not done": "missing", "not_done": "missing", "empty": "missing",
    "skipped": "missing",
    "half": "partial", "partially": "partial",
}


def _reconcile(score: int, verdict: str) -> tuple[int, str]:
    """Make the score and the verdict tell the same story.

    Models sometimes answer with a 0-5 scale (``"score": 1``) or simply
    contradict themselves (`score: 1` + `verdict: partial`). The categorical
    verdict is the more reliable field, so the score is clamped into the
    verdict's band — points, grades and reports then always agree.
    """
    if verdict == "unclear":
        return 0, "unclear"
    low, high = VERDICT_BANDS[verdict]
    return max(low, min(high, score)), verdict


def _clean_tasks(value: Any) -> list[dict[str, Any]]:
    """Keep task rows readable: known status vocabulary, nothing else."""
    out: list[dict[str, Any]] = []
    for item in _as_dict_list(value)[:20]:
        status = str(item.get("status", "") or "").strip().lower()
        status = _TASK_ALIASES.get(status, status)
        item["status"] = status if status in _TASK_STATUSES else "partial"
        out.append(item)
    return out


def _fallback(student_text: str, lang: str, reason: str) -> CheckResult:
    """Offline safety net: useful feedback now, manual grade by the teacher."""
    text = (student_text or "").strip()
    mistakes: list[dict[str, Any]] = []
    summary = (
        "AI tekshiruvi vaqtincha ishlamadi, ish o'qituvchi tomonidan qo'lda baholanadi."
        if lang == "uz"
        else "Automatic check is unavailable right now — the teacher will grade it manually."
    )
    lowered = text.lower()
    checks = (
        ("i ", "I ", "capitalisation", "The pronoun 'I' is always a capital letter."),
        ("alot", "a lot", "spelling", "'a lot' is always two words."),
        ("dont", "don't", "punctuation", "Short forms need an apostrophe: don't."),
        ("cant", "can't", "punctuation", "Short forms need an apostrophe: can't."),
        (" he go", " he goes", "tense", "Present Simple: he/she/it takes verb + s."),
        (" she go", " she goes", "tense", "Present Simple: he/she/it takes verb + s."),
    )
    for needle, fix, category, note in checks:
        if needle in lowered:
            mistakes.append({
                "original": needle.strip(),
                "correction": fix.strip(),
                "category": category,
                "rule": "",
                "explanation": note,
                "severity": "minor",
            })
    if text and text[0].islower():
        mistakes.append({
            "original": text[:24],
            "correction": text[:1].upper() + text[1:24],
            "category": "capitalisation",
            "rule": "Start a sentence with a capital letter",
            "explanation": "Every sentence and every name starts with a capital letter.",
            "severity": "minor",
        })
    if text and text[-1:] not in ".!?\"'":
        mistakes.append({
            "original": text[-24:],
            "correction": text[-24:] + ".",
            "category": "punctuation",
            "rule": "Full stop at the end of a sentence",
            "explanation": "Finish every sentence with . ? or !",
            "severity": "minor",
        })
    tips = [] if len(text.split()) >= 5 else ["Write full sentences — a short answer cannot be checked properly."]
    return CheckResult(
        ok=False,
        verdict="unclear",
        summary=summary,
        mistakes=mistakes[:8],
        tips=tips,
        error=reason,
        raw={"fallback": True, "reason": reason},
    )


async def generate_test(
    topics: Sequence[str],
    count: int = 10,
    lang: str = "bi",
    level: str = "",
    taught: Sequence[str] = (),
) -> list[dict[str, Any]]:
    """Build multiple-choice questions from the lessons already taught.

    Returns ``[{question, options[4], correct, explanation}, ...]`` — an empty
    list means the AI is unavailable (the teacher can add questions manually).
    """
    if not settings.ai_ready:
        return []
    syllabus = ", ".join(topics) if topics else "general revision of the course"
    taught_text = ", ".join(taught) if taught else "not recorded"
    prompt = (
        f"Create {count} multiple-choice questions for an English class.\n"
        f"Topics to test: {syllabus}.\n"
        f"Lessons given so far: {taught_text}.\n"
        f"Target level: {level or 'unknown (A2-B1)'}.\n"
        "Rules:\n"
        "- Each question has EXACTLY 4 short options, only one is correct.\n"
        "- Use the topic vocabulary and grammar, not trivia.\n"
        "- Vary the difficulty: some easy, some harder.\n"
        "- `explanation` is one short sentence in Uzbek explaining the answer "
        "when the student is wrong.\n"
        "- `correct` is the 0-based index of the right option.\n"
        "Reply with ONE JSON object only:\n"
        '{"questions": [{"question": "...", "options": ["a","b","c","d"], '
        '"correct": 0, "explanation": "..."}]}'
    )
    try:
        client = _client()
        response = await client.chat.completions.create(
            model=settings.ai_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
            max_tokens=2000,
        )
        payload = extract_json(response.choices[0].message.content or "")
        if payload is None:
            return []
        return _clean_questions(payload.get("questions"), count)
    except Exception:
        return []


def _clean_questions(raw: Any, count: int) -> list[dict[str, Any]]:
    """Validate the model's output so a single bad row cannot break the quiz."""
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = str(item.get("question") or "").strip()
        options = [str(o).strip() for o in (item.get("options") or [])[:4]]
        if not text or len(options) != 4 or not all(options):
            continue
        try:
            correct = int(item.get("correct", 0))
        except (TypeError, ValueError):
            correct = 0
        out.append({
            "question": text[:500],
            "options": options,
            "correct": max(0, min(3, correct)),
            "explanation": str(item.get("explanation") or "").strip()[:500],
        })
        if len(out) >= count:
            break
    return out


async def suggest_extra_task(
    homework: Any, mistakes: Sequence[dict[str, Any]] = (), lang: str = "bi"
) -> str:
    """Generate a short practice task, used as a penalty for missing homework."""
    rules = ", ".join(str(m.get("rule") or m.get("category") or "") for m in mistakes[:3] if m)
    topic = getattr(homework, "title", "") or getattr(homework, "topic", "") or "this lesson"
    template = (
        f"Write 10 sentences using '{topic}'"
        f"{' (' + rules + ')' if rules else ''} in your notebook "
        f"and send a photo of it to the group."
    )
    if not settings.ai_ready:
        return template
    prompt = (
        "You are an English teacher. A student did not do their homework. "
        f"Lesson topic: {topic}. Skill: {getattr(homework, 'skill', '') or 'general'}. "
        f"Their typical mistakes: {rules or 'not known'}. "
        "Give ONE short practice task (at most 2 sentences, in English, doable in "
        "20 minutes, must be submitted in writing). Reply with the task text only."
    )
    try:
        client = _client()
        response = await client.chat.completions.create(
            model=settings.ai_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=200,
        )
        text = (response.choices[0].message.content or "").strip()
        return text or template
    except Exception:
        return template
