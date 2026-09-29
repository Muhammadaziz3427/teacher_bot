"""Translations must stay complete for all three languages."""
from __future__ import annotations

from app.i18n import CATALOG, DEFAULT_LANG, grade_for, lang_display, normalize_lang, t, verdict_label


def test_catalog_has_every_language():
    missing = [key for key, entry in CATALOG.items()
               if not entry.get("en") or not entry.get("uz")]
    assert not missing, f"keys without en/uz text: {missing[:10]}"


def test_default_language_exists_in_the_catalog():
    assert DEFAULT_LANG in CATALOG[DEFAULT_LANG] if DEFAULT_LANG in ("en", "uz") else True
    assert DEFAULT_LANG in ("uz", "en", "bi")


def test_unknown_key_is_returned_as_is():
    assert t("definitely_missing_key", "uz") == "definitely_missing_key"


def test_blok4_keys_exist_in_every_language():
    for key in (
        "btn_submitted", "btn_not_yet", "btn_parent_link", "btn_open_dashboard",
        "voice_listening", "voice_saved", "voice_empty", "voice_too_big",
        "voice_not_ready", "sub_confirm_ask", "sub_confirm_ok",
        "sub_confirm_cancelled", "sub_confirm_denied", "sub_confirm_missing",
        "parent_link_ready", "parent_link_no_username", "parent_link_sent",
        "parent_link_denied", "parent_link_unknown",
        "app_open_title", "app_open_off", "app_open_https",
        "app_pick_group", "app_chat_title",
    ):
        for lang in ("uz", "en", "bi"):
            text = t(key, lang)
            assert text and text != key, f"{key} missing in {lang}"


def test_format_never_raises_on_missing_arguments():
    text = t("fb_score", "uz")          # expects {score} and {grade}
    assert isinstance(text, str) and text


def test_existing_arguments_are_formatted():
    assert "92" in t("fb_score", "uz", score=92, grade="A")


def test_language_aliases():
    assert normalize_lang("o'zbek") == "uz"
    assert normalize_lang("English") == "en"
    assert normalize_lang("bi") == "bi"
    assert normalize_lang("whatever") == DEFAULT_LANG


def test_language_display_is_human_readable():
    assert "Uzbek" in lang_display("uz")
    assert lang_display("xx") == "xx"


def test_grade_boundaries():
    assert grade_for(90) == "A"
    assert grade_for(89) == "B"
    assert grade_for(80) == "B"
    assert grade_for(79) == "C"
    assert grade_for(65) == "C"
    assert grade_for(64) == "D"
    assert grade_for(50) == "D"
    assert grade_for(49) == "E"


def test_verdict_labels_for_every_mode():
    for lang in ("uz", "en", "bi"):
        for verdict in ("correct", "partial", "wrong", "unclear"):
            assert verdict_label(verdict, lang)