"""catalog -- pure domain policies: the validation engine [P] (DB Architecture Sec 14.3:
"AttributeSet vs FormDefinition version -- validation engine [P] in catalog, executing configured
rules [C]"), slug derivation, and the duplicate-detection title comparator. No I/O, no repository
access -- callers (`application/`) fetch whatever data these functions need and pass it in,
exactly the boundary `media.domain.media_asset`'s own module docstring describes for its
`ImageOnlyPolicy`/size check versus catalog's own I-07 check needing configuration data first.
"""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from catalog.domain.exceptions import AttributeValidationError
from catalog.domain.value_objects import FieldValidatorSpec

_SLUG_UNSAFE = re.compile(r"[^a-z0-9]+")
_WHITESPACE = re.compile(r"\s+")


def generate_slug(title: str, listing_id: UUID) -> str:
    """Display-only (Physical DB: "slug ... display-only, Logical Sec 10") -- no documented
    uniqueness constraint exists on this column, so a short id suffix (not a DB round-trip) is
    enough to make it visually distinct without a global-uniqueness lookup."""
    base = _SLUG_UNSAFE.sub("-", title.strip().lower()).strip("-") or "listing"
    suffix = str(listing_id).split("-")[0]
    return f"{base}-{suffix}"


def validate_attribute_set(
    attributes: dict[str, Any],
    specs: tuple[FieldValidatorSpec, ...],
    *,
    image_count: int,
    field_codes: frozenset[str] | None = None,
) -> None:
    """Executes every configured rule [C] against the submitted AttributeSet (I-07, DB
    Architecture Sec 14.3). Implements exactly the six `validator_type`s
    `configuration.interfaces.dto.ValidatorBinding` declares -- no more, no less
    (`catalog.domain.value_objects.ValidatorType`). Raises `AttributeValidationError` collecting
    every failure at once (one round-trip for the caller to display), not just the first.

    UNF-020: `attributes` is contractually "typed values keyed by the field `code` of the bound
    FormDefinition version" -- a key the form never declared has no configured rule to fail, so
    without this check it sailed through unrejected, was persisted, and got projected into the
    search index. `field_codes` is optional only so existing unit tests that build a `specs`
    tuple by hand without a full form snapshot don't all need updating; every real caller
    (`ConfigurationCategoryFormAdapter`) always supplies it."""
    failures: list[str] = []

    if field_codes is not None:
        for unknown in sorted(set(attributes) - field_codes):
            failures.append(f"{unknown}: not a field of the bound form")

    for spec in specs:
        if spec.required_field and spec.field_code not in attributes:
            failures.append(f"{spec.field_code}: field is required")

    for spec in specs:
        value = attributes.get(spec.field_code)
        if spec.validator_type == "required":
            if value is None or (isinstance(value, str) and not value.strip()):
                failures.append(f"{spec.field_code}: required")
        elif spec.validator_type == "length" and value is not None:
            _check_length(spec, value, failures)
        elif spec.validator_type == "numeric_range" and value is not None:
            _check_numeric_range(spec, value, failures)
        elif spec.validator_type == "pattern_safe" and value is not None:
            _check_pattern_safe(spec, value, failures)
        elif spec.validator_type == "option_membership" and value is not None:
            _check_option_membership(spec, value, failures)
        elif spec.validator_type == "image_count":
            _check_image_count(spec, image_count, failures)

    if failures:
        raise AttributeValidationError(tuple(failures))


def _check_length(spec: FieldValidatorSpec, value: Any, failures: list[str]) -> None:
    length = len(str(value))
    minimum = spec.params.get("min")
    maximum = spec.params.get("max")
    if minimum is not None and length < minimum:
        failures.append(f"{spec.field_code}: shorter than {minimum} characters")
    if maximum is not None and length > maximum:
        failures.append(f"{spec.field_code}: longer than {maximum} characters")


def _check_numeric_range(spec: FieldValidatorSpec, value: Any, failures: list[str]) -> None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        failures.append(f"{spec.field_code}: must be numeric")
        return
    minimum = spec.params.get("min")
    maximum = spec.params.get("max")
    if minimum is not None and numeric < minimum:
        failures.append(f"{spec.field_code}: below minimum {minimum}")
    if maximum is not None and numeric > maximum:
        failures.append(f"{spec.field_code}: above maximum {maximum}")


def _check_pattern_safe(spec: FieldValidatorSpec, value: Any, failures: list[str]) -> None:
    pattern = spec.params.get("pattern")
    if pattern and (not isinstance(value, str) or re.fullmatch(pattern, value) is None):
        failures.append(f"{spec.field_code}: does not match the required pattern")


def _check_option_membership(spec: FieldValidatorSpec, value: Any, failures: list[str]) -> None:
    allowed = spec.params.get("options", [])
    values = value if isinstance(value, list) else [value]
    for candidate in values:
        if candidate not in allowed:
            failures.append(f"{spec.field_code}: {candidate!r} is not an allowed option")


def _check_image_count(spec: FieldValidatorSpec, image_count: int, failures: list[str]) -> None:
    minimum = spec.params.get("min")
    maximum = spec.params.get("max")
    if minimum is not None and image_count < minimum:
        failures.append(f"images: at least {minimum} required")
    if maximum is not None and image_count > maximum:
        failures.append(f"images: at most {maximum} allowed")


def normalize_title_for_duplicate_matching(title: str) -> str:
    """FR-ADV-009/DuplicateDetectionService: "configurable-rule matching" -- no literal matching
    algorithm is specified anywhere in the approved documents (same class of gap as identity's
    P-05 OTP-throttle constants, resolved there as implementation-chosen). This task's own
    minimal, defensible heuristic: exact match on a normalised (case/whitespace-folded) title
    within the same owner + category -- `application/duplicate_detection_service.py` supplies the
    "same owner + category" scoping via a repository query; this function is the pure comparator."""
    return _WHITESPACE.sub(" ", title.strip().lower())
