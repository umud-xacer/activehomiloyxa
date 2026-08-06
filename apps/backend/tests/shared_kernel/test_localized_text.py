"""LocalizedText -- round-trips all four locales/scripts (DEC-19); no field is required."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from shared_kernel import LocalizedText


def test_all_four_locales_round_trip() -> None:
    text = LocalizedText(uz_latn="Kvartira", uz_cyrl="Квартира", ru="Квартира", en="Apartment")
    wire = text.model_dump(mode="json")
    assert wire == {
        "uz_latn": "Kvartira",
        "uz_cyrl": "Квартира",
        "ru": "Квартира",
        "en": "Apartment",
    }
    assert LocalizedText.model_validate(wire) == text


@pytest.mark.parametrize("field", ["uz_latn", "uz_cyrl", "ru", "en"])
def test_each_locale_is_independently_optional(field: str) -> None:
    text = LocalizedText(**{field: "x"})
    assert getattr(text, field) == "x"
    other_fields = {"uz_latn", "uz_cyrl", "ru", "en"} - {field}
    assert all(getattr(text, f) is None for f in other_fields)


def test_no_locale_is_required() -> None:
    text = LocalizedText()
    assert text.uz_latn is None
    assert text.uz_cyrl is None
    assert text.ru is None
    assert text.en is None


def test_equal_values_are_equal_and_hash_equal() -> None:
    a = LocalizedText(uz_latn="Kvartira", en="Apartment")
    b = LocalizedText(uz_latn="Kvartira", en="Apartment")
    assert a == b
    assert hash(a) == hash(b)


def test_is_immutable() -> None:
    text = LocalizedText(uz_latn="Kvartira")
    with pytest.raises(ValidationError):
        text.uz_latn = "Changed"  # type: ignore[misc]


def test_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        LocalizedText.model_validate({"fr": "Appartement"})
