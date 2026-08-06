"""Unit tests for `ConfigurationCategoryFormAdapter`/`ConfigurationPlatformSettingsAdapter`
against fakes of the narrow slices they actually call -- no real Postgres needed. Mirrors
`apps/backend/tests/identity/test_configuration_adapter.py`'s pattern.

`_flatten_specs`'s fixture snapshots are shaped exactly like
`configuration.domain.content.FormDefinitionContent` actually serializes (`fields` a top-level
array, each field carrying its own `section_code` -- NOT nested under `sections`, per that
model's own module docstring) -- this is a deliberate regression test: an earlier version of
`_flatten_specs` iterated `section["fields"]`, which is never populated in the real snapshot
shape and silently produced an always-empty spec tuple (I-07's validation engine never actually
firing against a real configured form)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest

from catalog.infrastructure.configuration_adapter import (
    ConfigurationCategoryFormAdapter,
    ConfigurationPlatformSettingsAdapter,
)
from configuration.interfaces.dto import (
    ConfigurationHead,
    ConfigurationHeadPage,
    ConfigurationVersion,
    PageInfo,
)


@dataclass
class FakeCategoryReader:
    """Implements `catalog.infrastructure.configuration_adapter._CategoryReader`."""

    categories: dict[UUID, dict[str, Any] | None] = field(default_factory=dict)
    forms: dict[UUID, dict[str, Any] | None] = field(default_factory=dict)

    async def get_category(self, category_id: UUID) -> dict[str, Any] | None:
        return self.categories.get(category_id)

    async def get_category_form(self, category_id: UUID) -> dict[str, Any] | None:
        return self.forms.get(category_id)


@dataclass
class FakePlatformSettingsReader:
    heads: list[ConfigurationHead] = field(default_factory=list)
    versions: dict[UUID, ConfigurationVersion] = field(default_factory=dict)

    async def list_config_heads(
        self, entity_type: str, cursor: str | None = None, limit: int | None = 20
    ) -> ConfigurationHeadPage:
        matching = [h for h in self.heads if h.entity_type == entity_type]
        return ConfigurationHeadPage(
            items=matching, page=PageInfo(limit=limit or 20, next_cursor=None)
        )

    async def get_config_version(
        self, entity_type: str, head_id: UUID, version_id: UUID
    ) -> ConfigurationVersion:
        return self.versions[version_id]


def _real_shaped_form_snapshot(*, form_id: UUID, version_id: UUID) -> dict[str, Any]:
    """`configuration.application.use_cases.ConfigurationUseCases._build_snapshot`'s own output
    shape: `**version.definition_document` spread flat, plus `id`/`versionId` injected. The
    `definition_document` half matches `configuration.domain.content.FormDefinitionContent`
    exactly -- `sections` and `fields` are SIBLING top-level keys, not nested."""
    return {
        "id": str(form_id),
        "versionId": str(version_id),
        "descriptor": {"name": {"en": "Apartment form"}},
        "sections": [{"code": "basics", "label": {"en": "Basics"}, "order": 0}],
        "fields": [
            {
                "code": "rooms",
                "section_code": "basics",
                "label": {"en": "Rooms"},
                "field_type": "number",
                "required": True,
                "validators": [
                    {"validator_type": "numeric_range", "params": {"min": 1, "max": 10}},
                ],
            },
            {
                "code": "title",
                "section_code": "basics",
                "label": {"en": "Title"},
                "field_type": "text",
                "required": False,
                "validators": [
                    {"validator_type": "length", "params": {"min": 5, "max": 100}},
                ],
            },
        ],
    }


async def test_get_current_form_binding_flattens_the_real_top_level_fields_shape() -> None:
    category_id = uuid4()
    form_id, version_id = uuid4(), uuid4()
    reader = FakeCategoryReader(
        forms={category_id: _real_shaped_form_snapshot(form_id=form_id, version_id=version_id)}
    )

    adapter = ConfigurationCategoryFormAdapter(reader)
    binding = await adapter.get_current_form_binding(category_id)

    assert binding is not None
    assert binding.form_definition_id == form_id
    assert binding.form_definition_version_id == version_id
    # "rooms" is required (synthesizes a leading `required` spec) plus its own numeric_range;
    # "title" carries only its configured `length` validator. Nesting under `sections` (the bug
    # this test guards against) would silently produce an empty tuple here instead.
    assert len(binding.specs) == 3
    field_codes = {spec.field_code for spec in binding.specs}
    assert field_codes == {"rooms", "title"}
    validator_types = {spec.validator_type for spec in binding.specs}
    assert validator_types == {"required", "numeric_range", "length"}
    required_spec = next(s for s in binding.specs if s.validator_type == "required")
    assert required_spec.field_code == "rooms"
    assert required_spec.required_field is True
    # UNF-020: field_codes covers every declared field, not just ones with a validator (a
    # field's own presence, validator-less or not, is what makes an attribute key legitimate).
    # Compared as a `frozenset`, matching the port's declared `frozenset[str] | None`: a bare set
    # literal is a different nominal type, which `--strict` rejects as a non-overlapping equality
    # check even though the two compare equal at runtime.
    assert binding.field_codes == frozenset({"rooms", "title"})


async def test_get_current_form_binding_wires_field_options_into_option_membership_params() -> None:
    """UNF-002: `option_membership` validates against the FIELD's own configured `options`
    (`configuration.domain.content.FormFieldContent.options`, a sibling of `validators` -- not
    nested under a binding's own `params`, since there is nowhere else to author them). Before
    this fix `_flatten_specs` never read `field["options"]` at all, so `params["options"]` was
    always absent and `_check_option_membership` rejected every value."""
    category_id = uuid4()
    form_id, version_id = uuid4(), uuid4()
    snapshot = {
        "id": str(form_id),
        "versionId": str(version_id),
        "descriptor": {"name": {"en": "Materials form"}},
        "sections": [{"code": "basics", "label": {"en": "Basics"}, "order": 0}],
        "fields": [
            {
                "code": "condition",
                "section_code": "basics",
                "label": {"en": "Condition"},
                "field_type": "select",
                "required": False,
                "options": [
                    {"value": "new", "label": {"en": "New"}},
                    {"value": "used", "label": {"en": "Used"}},
                ],
                "validators": [{"validator_type": "option_membership", "params": {}}],
            },
        ],
    }
    reader = FakeCategoryReader(forms={category_id: snapshot})

    adapter = ConfigurationCategoryFormAdapter(reader)
    binding = await adapter.get_current_form_binding(category_id)

    assert binding is not None
    spec = next(s for s in binding.specs if s.validator_type == "option_membership")
    assert spec.params["options"] == ["new", "used"]


async def test_get_current_form_binding_returns_none_when_no_form_bound() -> None:
    reader = FakeCategoryReader()
    adapter = ConfigurationCategoryFormAdapter(reader)
    assert await adapter.get_current_form_binding(uuid4()) is None


async def test_get_category_maps_status_and_form_head_id() -> None:
    category_id = uuid4()
    form_id = uuid4()
    reader = FakeCategoryReader(
        categories={
            category_id: {
                "path": "/real-estate/apartments",
                "tree_status": "ACTIVE",
                "form_definition_id": str(form_id),
            }
        }
    )
    adapter = ConfigurationCategoryFormAdapter(reader)
    snapshot = await adapter.get_category(category_id)
    assert snapshot is not None
    assert snapshot.path == "/real-estate/apartments"
    assert snapshot.status == "ACTIVE"
    assert snapshot.form_definition_head_id == form_id


async def test_get_category_returns_none_when_unknown() -> None:
    reader = FakeCategoryReader()
    adapter = ConfigurationCategoryFormAdapter(reader)
    assert await adapter.get_category(uuid4()) is None


def _head(entity_type: str, code: str, version_id: UUID) -> ConfigurationHead:
    return ConfigurationHead(
        id=uuid4(),
        entity_type=entity_type,  # type: ignore[arg-type]
        code=code,
        current_version_id=version_id,
        status="PUBLISHED",
        business_owner="Super Administrator",
        created_at=None,
    )


def _version(head_id: UUID, version_id: UUID, snapshot: dict[str, object]) -> ConfigurationVersion:
    return ConfigurationVersion(
        id=version_id,
        head_id=head_id,
        version_number=1,
        status="PUBLISHED",
        definition={},
        snapshot=snapshot,
    )


async def test_get_catalog_settings_reads_default_expiry_days() -> None:
    version_id = uuid4()
    head = _head("platform-settings", "platform-settings-global", version_id)
    version = _version(head.id, version_id, {"settings": {"listing.default_expiry_days": 45}})
    reader = FakePlatformSettingsReader(heads=[head], versions={version_id: version})

    adapter = ConfigurationPlatformSettingsAdapter(reader)
    settings = await adapter.get_catalog_settings()
    assert settings.default_expiry_days == 45


async def test_get_catalog_settings_no_published_head_raises() -> None:
    reader = FakePlatformSettingsReader()
    adapter = ConfigurationPlatformSettingsAdapter(reader)
    with pytest.raises(LookupError):
        await adapter.get_catalog_settings()
