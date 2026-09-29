"""Speech-to-text for voice homework.

OpenRouter (and most chat-completion providers) has no audio endpoint, so the
transcription runs against its own key — ``STT_API_KEY`` / ``STT_BASE_URL``
(OpenAI ``whisper-1`` by default) and falls back to ``OPENAI_API_KEY``.
Everything degrades quietly: a failed or oversized voice note returns an
empty transcript and the student is asked to write instead.
"""

from __future__ import annotations

import logging
from typing import Any

from .config import settings

log = logging.getLogger(__name__)

MAX_VOICE_BYTES = 20 * 1024 * 1024   # Whisper accepts up to 25 MB
_CLIENT: Any = None


def is_voice_ready() -> bool:
    return settings.stt_ready


def too_large(size: int | None) -> bool:
    """True when a Telegram voice file is bigger than the STT limit."""
    return bool(size) and int(size) > MAX_VOICE_BYTES


def _client():
    global _CLIENT
    if _CLIENT is None:
        from openai import AsyncOpenAI

        _CLIENT = AsyncOpenAI(
            api_key=settings.stt_api_key or settings.openai_api_key,
            base_url=settings.stt_endpoint,
            timeout=settings.ai_timeout,
        )
    return _CLIENT


async def transcribe(
    blob: bytes, filename: str = "voice.ogg", mime: str = "audio/ogg"
) -> str:
    """Return what the student said (may be empty) — never raises."""
    if not blob or too_large(len(blob)):
        return ""
    try:
        response = await _client().audio.transcriptions.create(
            model=settings.stt_model, file=(filename, blob, mime)
        )
    except Exception as exc:
        log.warning("Transcription failed (%s): %s",
                    type(exc).__name__, str(exc)[:200])
        return ""
    return str(getattr(response, "text", "") or "").strip()


def combine(text: str, transcript: str, limit: int = 6000) -> str:
    """Merge a written caption and the spoken answer into one submission."""
    parts = [part.strip() for part in (text, transcript) if part and part.strip()]
    return " ".join(parts)[:limit]