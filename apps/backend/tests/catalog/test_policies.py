"""`catalog.domain.policies` -- the validation engine [P] executing configured rules [C]
(DB Architecture Sec 14.3), slug derivation, and the duplicate-detection title comparator."""

from __future__ import annotations

from uuid import uuid4

import pytest

from catalog.domain.exceptions import AttributeValidationError
from catalog.domain.policies import (
    generate_slug,
    normalize_title_for_duplicate_matching,
    validate_attribute_set,
)
from catalog.domain.value_objects import FieldValidatorSpec


def test_generate_slug_is_url_safe_and_suffixed_with_the_id() -> None:
    listing_id = uuid4()
    slug = generate_slug("Nice 2-Room Apartment!!", listing_id)
    assert slug.startswith("nice-2-room-apartment")
    assert slug.endswith(str(listing_id).split("-")[0])
    assert " " not in slug
    assert "!" not in slug


def test_generate_slug_falls_back_when_title_has_no_safe_characters() -> None:
    slug = generate_slug("!!!", uuid4())
    assert slug.startswith("listing-")


def test_validate_attribute_set_passes_when_all_rules_satisfied() -> None:
    specs = (
        FieldValidatorSpec(
            field_code="rooms", validator_type="required", params={}, required_field=True
        ),
        FieldValidatorSpec(
            field_code="rooms",
            validator_type="numeric_range",
            params={"min": 1, "max": 10},
            required_field=False,
        ),
    )
    validate_attribute_set({"rooms": 3}, specs, image_count=1)  # must not raise


def test_validate_attribute_set_collects_every_failure_not_just_the_first() -> None:
    specs = (
        FieldValidatorSpec(
            field_code="rooms",
            validator_type="numeric_range",
            params={"min": 1, "max": 5},
            required_field=False,
        ),
        FieldValidatorSpec(
            field_code="title", validator_type="length", params={"min": 5}, required_field=False
        ),
    )
    with pytest.raises(AttributeValidationError) as exc_info:
        validate_attribute_set({"rooms": 99, "title": "hi"}, specs, image_count=0)
    assert len(exc_info.value.failures) == 2


def test_validate_attribute_set_required_field_missing() -> None:
    specs = (
        FieldValidatorSpec(
            field_code="rooms", validator_type="required", params={}, required_field=True
        ),
    )
    with pytest.raises(AttributeValidationError) as exc_info:
        validate_attribute_set({}, specs, image_count=0)
    assert any("rooms" in f for f in exc_info.value.failures)


def test_validate_attribute_set_pattern_safe() -> None:
    specs = (
        FieldValidatorSpec(
            field_code="phone",
            validator_type="pattern_safe",
            params={"pattern": r"\+998\d{9}"},
            required_field=False,
        ),
    )
    validate_attribute_set({"phone": "+998901234567"}, specs, image_count=0)
    with pytest.raises(AttributeValidationError):
        validate_attribute_set({"phone": "not-a-phone"}, specs, image_count=0)


def test_validate_attribute_set_option_membership() -> None:
    specs = (
        FieldValidatorSpec(
            field_code="condition",
            validator_type="option_membership",
            params={"options": ["NEW", "USED"]},
            required_field=False,
        ),
    )
    validate_attribute_set({"condition": "NEW"}, specs, image_count=0)
    with pytest.raises(AttributeValidationError):
        validate_attribute_set({"condition": "REFURBISHED"}, specs, image_count=0)


def test_UNF_020_unknown_attribute_key_rejected_when_field_codes_supplied() -> None:
    """`AttributeMap` is contractually "typed values keyed by the field code of the bound
    FormDefinition version" -- a key the form never declared has no validator to fail it, so
    without an explicit field-code whitelist it was silently accepted, persisted, and projected
    into search."""
    specs = (
        FieldValidatorSpec(
            field_code="rooms", validator_type="required", params={}, required_field=True
        ),
    )
    field_codes = frozenset({"rooms"})

    validate_attribute_set({"rooms": 3}, specs, image_count=0, field_codes=field_codes)

    with pytest.raises(AttributeValidationError) as exc_info:
        validate_attribute_set(
            {"rooms": 3, "unknown_field": "x"}, specs, image_count=0, field_codes=field_codes
        )
    assert any("unknown_field" in failure for failure in exc_info.value.failures)


def test_UNF_020_unknown_attribute_key_ignored_when_field_codes_omitted() -> None:
    """`field_codes` is opt-in (`None` by default) precisely so callers/tests that don't model a
    full form snapshot aren't forced to -- only `attributes.keys()` vs an explicit whitelist is
    ever checked."""
    specs = (
        FieldValidatorSpec(
            field_code="rooms", validator_type="required", params={}, required_field=True
        ),
    )
    validate_attribute_set({"rooms": 3, "unknown_field": "x"}, specs, image_count=0)


def test_validate_attribute_set_image_count_bounds() -> None:
    specs = (
        FieldValidatorSpec(
            field_code="images",
            validator_type="image_count",
            params={"min": 1, "max": 10},
            required_field=False,
        ),
    )
    validate_attribute_set({}, specs, image_count=3)
    with pytest.raises(AttributeValidationError):
        validate_attribute_set({}, specs, image_count=0)
    with pytest.raises(AttributeValidationError):
        validate_attribute_set({}, specs, image_count=11)


def test_normalize_title_for_duplicate_matching_folds_case_and_whitespace() -> None:
    assert normalize_title_for_duplicate_matching("  Nice   Apartment  ") == "nice apartment"
    assert normalize_title_for_duplicate_matching("NICE APARTMENT") == "nice apartment"


def test_validate_attribute_set_length_upper_bound() -> None:
    specs = (
        FieldValidatorSpec(
            field_code="title", validator_type="length", params={"max": 5}, required_field=False
        ),
    )
    with pytest.raises(AttributeValidationError) as exc_info:
        validate_attribute_set({"title": "way too long"}, specs, image_count=0)
    assert any("longer than" in f for f in exc_info.value.failures)


def test_validate_attribute_set_numeric_range_non_numeric_value() -> None:
    specs = (
        FieldValidatorSpec(
            field_code="rooms",
            validator_type="numeric_range",
            params={"min": 1},
            required_field=False,
        ),
    )
    with pytest.raises(AttributeValidationError) as exc_info:
        validate_attribute_set({"rooms": "not-a-number"}, specs, image_count=0)
    assert any("must be numeric" in f for f in exc_info.value.failures)


def test_validate_attribute_set_numeric_range_below_minimum() -> None:
    specs = (
        FieldValidatorSpec(
            field_code="rooms",
            validator_type="numeric_range",
            params={"min": 5},
            required_field=False,
        ),
    )
    with pytest.raises(AttributeValidationError) as exc_info:
        validate_attribute_set({"rooms": 1}, specs, image_count=0)
    assert any("below minimum" in f for f in exc_info.value.failures)
