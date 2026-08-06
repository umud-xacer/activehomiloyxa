"""`_form_definition_dto_from_snapshot` -- the `getCategoryForm` wire mapping (DEF-04).

This layer had no coverage, which is why DEF-04 shipped: `tests/configuration/test_category_read.py`
exercises `CategoryReadUseCases.get_category_form`, but that returns the raw snapshot `dict` and
stops short of the DTO mapping where the bug lived. The `minimal_content("form-definition")`
fixture also carries `"fields": []`, and the failure needs at least one field to trigger -- so even
a test that had reached the mapper would have passed with the standard fixture.

Both gaps are closed here: the mapper is called directly, with fields.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from configuration.interfaces.routers import _form_definition_dto_from_snapshot

FORM_ID = uuid4()
VERSION_ID = uuid4()
CATEGORY_ID = uuid4()


def _field(code: str, section_code: str, order: int, **overrides: Any) -> dict[str, Any]:
    """A stored field snapshot, shaped exactly like `FormFieldContent.model_dump()`.

    `section_code` is the point of the whole fixture: every stored field has one (the gate in
    `configuration/domain/gate.py` rejects a field whose `section_code` names no section), and the
    contract's `FormField` does not declare it.
    """
    return {
        "code": code,
        "section_code": section_code,
        "label": {"uz_latn": code.title()},
        "field_type": "text",
        "required": False,
        "facet_eligible": False,
        "order": order,
        "default_value": None,
        "options": [],
        "validators": [],
        "rendering_hint": None,
        "conditional_visibility": None,
        **overrides,
    }


def _snapshot(fields: list[dict[str, Any]]) -> dict[str, Any]:
    """Mirrors `ConfigurationUseCases._snapshot_document`: the published definition document plus
    camelCase metadata keys. Sections are intentionally listed out of `order` so the mapper's own
    sorting is exercised rather than the fixture's insertion order."""
    return {
        "descriptor": {"name": {"uz_latn": "Housing form"}},
        "sections": [
            {"code": "specs", "label": {"uz_latn": "Specifications"}, "order": 2},
            {"code": "main", "label": {"uz_latn": "Main"}, "order": 1},
        ],
        "fields": fields,
        "id": str(FORM_ID),
        "code": "housing-form",
        "entityType": "form-definition",
        "versionId": str(VERSION_ID),
        "versionNumber": 1,
        "publishedAt": "2026-07-26T00:00:00+00:00",
    }


def test_maps_a_form_whose_fields_carry_section_code() -> None:
    """DEF-04: this raised `ValidationError` for every field of every form before the fix.

    `FormField` inherits `CamelModel`'s `extra="forbid"`, so passing the raw snapshot dict --
    which always includes `section_code` -- straight into `model_validate` failed unconditionally,
    surfacing as `GET /categories/{id}/form` -> `500 DEPENDENCY_DEGRADED` for every category.
    """
    dto = _form_definition_dto_from_snapshot(
        _snapshot([_field("rooms", "main", 1)]), category_id=CATEGORY_ID
    )

    assert dto.id == FORM_ID
    assert dto.version_id == VERSION_ID
    assert dto.category_id == CATEGORY_ID
    assert [s.code for s in dto.sections] == ["main", "specs"]
    assert [f.code for f in dto.sections[0].fields] == ["rooms"]


def test_section_code_is_not_leaked_onto_the_response() -> None:
    """The fix drops `section_code` rather than adding it to the DTO.

    Adding it would make the response carry a property the contract's `FormField` does not
    declare, trading a 500 for a contract-conformance failure (QG-06). The section nesting the
    caller receives already expresses the grouping.
    """
    dto = _form_definition_dto_from_snapshot(
        _snapshot([_field("rooms", "main", 1)]), category_id=CATEGORY_ID
    )

    field = dto.sections[0].fields[0]
    assert not hasattr(field, "section_code")
    assert "sectionCode" not in dto.model_dump(by_alias=True)["sections"][0]["fields"][0]
    assert "section_code" not in dto.model_dump()["sections"][0]["fields"][0]


def test_groups_fields_into_their_own_section_and_orders_both() -> None:
    dto = _form_definition_dto_from_snapshot(
        _snapshot(
            [
                _field("area", "specs", 2),
                _field("rooms", "main", 2),
                _field("floor", "specs", 1),
                _field("title", "main", 1),
            ]
        ),
        category_id=CATEGORY_ID,
    )

    by_code = {section.code: section for section in dto.sections}
    assert [f.code for f in by_code["main"].fields] == ["title", "rooms"]
    assert [f.code for f in by_code["specs"].fields] == ["floor", "area"]


def test_maps_a_field_carrying_options_validators_and_conditional_visibility() -> None:
    """The richest field shape the whitelist permits -- these nested models are the most likely
    place for a second `extra="forbid"` mismatch to hide."""
    dto = _form_definition_dto_from_snapshot(
        _snapshot(
            [
                _field(
                    "heating",
                    "specs",
                    1,
                    field_type="select",
                    required=True,
                    facet_eligible=True,
                    options=[
                        {"value": "gas", "label": {"uz_latn": "Gaz"}},
                        {"value": "electric", "label": {"uz_latn": "Elektr"}},
                    ],
                    validators=[{"validator_type": "option_membership", "params": {}}],
                    conditional_visibility={
                        "field_code": "rooms",
                        "operator": "GREATER_THAN",
                        "value": 1,
                    },
                    rendering_hint="two-column",
                )
            ]
        ),
        category_id=CATEGORY_ID,
    )

    field = dto.sections[1].fields[0]
    assert field.field_type == "select"
    assert field.required is True
    assert field.facet_eligible is True
    assert [o.value for o in field.options or []] == ["gas", "electric"]
    assert [v.validator_type for v in field.validators or []] == ["option_membership"]
    assert field.conditional_visibility is not None
    assert field.conditional_visibility.field_code == "rooms"
    assert field.rendering_hint == "two-column"


def test_a_form_with_no_fields_still_maps() -> None:
    """The shape `minimal_content("form-definition")` produces -- it worked before the fix too,
    which is exactly why the defect stayed hidden. Kept so the fix doesn't regress it."""
    dto = _form_definition_dto_from_snapshot(_snapshot([]), category_id=CATEGORY_ID)

    assert [s.code for s in dto.sections] == ["main", "specs"]
    assert all(s.fields == [] for s in dto.sections)


def test_a_field_naming_an_unknown_section_is_dropped_not_crashed() -> None:
    """The gate rejects this at publish time, so it should be unreachable -- but the mapper is a
    read path over already-stored data, and a snapshot written before a gate rule existed must not
    500 the endpoint."""
    dto = _form_definition_dto_from_snapshot(
        _snapshot([_field("rooms", "main", 1), _field("ghost", "no-such-section", 1)]),
        category_id=CATEGORY_ID,
    )

    assert [f.code for section in dto.sections for f in section.fields] == ["rooms"]


@pytest.mark.parametrize("category_id", [None, CATEGORY_ID])
def test_category_id_comes_from_the_caller_never_the_snapshot(category_id: UUID | None) -> None:
    """A form carries no back-reference to the category that binds it (the binding is
    one-directional, `category.form_definition_id`), so the route supplies it."""
    dto = _form_definition_dto_from_snapshot(
        _snapshot([_field("rooms", "main", 1)]), category_id=category_id
    )

    assert dto.category_id == category_id
