"""Locale -- the four locale/script codes (DEC-19), matching LocalizedText's field names."""

from __future__ import annotations

from shared_kernel import Locale, LocalizedText


def test_locale_values_match_localized_text_field_names() -> None:
    assert {loc.value for loc in Locale} == set(LocalizedText.model_fields.keys())


def test_locale_is_a_string_enum() -> None:
    assert Locale.UZ_LATN == "uz_latn"  # type: ignore[comparison-overlap]
    assert isinstance(Locale.UZ_LATN, str)
