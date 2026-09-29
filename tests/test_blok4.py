"""Voice answers, confirmation flow, deep links and the mini app."""
from __future__ import annotations

from app import deeplink
from app import stt


def test_too_large_rejects_massive_files():
    assert stt.too_large(30 * 1024 * 1024) is True
    assert stt.too_large(1024) is False
    assert stt.too_large(None) is False
    assert stt.too_large(0) is False


def test_combine_joins_caption_and_transcript():
    assert stt.combine("write this", "i say this") == "write this i say this"
    assert stt.combine("", "i say this") == "i say this"
    assert stt.combine("write this", "") == "write this"
    assert stt.combine("", "") == ""
    assert len(stt.combine("x" * 9000, "y" * 9000)) <= 6000


def test_parent_payload_round_trip():
    payload = deeplink.build_parent_payload(-1001234567890, 101)
    assert payload == "parent_1001234567890_101"
    assert deeplink.parse_parent_payload(payload) == (-1001234567890, 101)


def test_parent_payload_rejects_junk():
    assert deeplink.parse_parent_payload("") is None
    assert deeplink.parse_parent_payload("parent_") is None
    assert deeplink.parse_parent_payload("parent_x_y") is None
    assert deeplink.parse_parent_payload("parent_10_-5") is None
    assert deeplink.parse_parent_payload("other_10_5") is None
    assert deeplink.parse_parent_payload(None) is None


def test_parent_url_uses_the_bot_name():
    url = deeplink.parent_url("@teacherbot", -1001234567890, 101)
    assert url == "https://t.me/teacherbot?start=parent_1001234567890_101"
    assert deeplink.parent_url("", -1001234567890, 101) == ""


def test_transcription_endpoint_falls_back_to_the_main_provider():
    """No STT_BASE_URL → voice notes use the AI provider's base URL."""
    from app.config import settings

    assert settings.stt_endpoint == (settings.stt_base_url
                                     or settings.openai_base_url)


def test_voice_size_limit_matches_the_provider_ceiling():
    assert stt.MAX_VOICE_BYTES == 20 * 1024 * 1024
    assert stt.too_large(stt.MAX_VOICE_BYTES) is False
    assert stt.too_large(stt.MAX_VOICE_BYTES + 1) is True