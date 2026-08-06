"""Reads published Category/FormDefinition snapshots and the `platform-settings-global` snapshot
from `configuration` -- never `configuration.domain`/`infrastructure` (`cross-module-catalog`,
tools/importlinter.cfg). Mirrors `identity.infrastructure.configuration_adapter`'s own pattern:
a narrow Protocol naming only the calls this module actually makes, satisfied by a bridge object
the composition root supplies (the one place allowed to see both modules' internals at once).

Bridges directly to `configuration.application.category_read.CategoryReadUseCases.get_category`/
`get_category_form` (both already return `dict[str, Any] | None`, the resolved consumer-facing
snapshot) rather than the DTO-typed `configuration.interfaces.ports.ConfigurationPort` -- that
Protocol's own `get_category`/`get_category_form` return non-optional DTOs (a 404 is an HTTP
concern raised by its own router, not an in-process signal this adapter could branch on); the
application-layer read use case's `None` return is the actual "not found" signal `CategoryFormPort`
needs. The resolved snapshot's *outer* bookkeeping keys are camelCase (`configuration.application.
use_cases.ConfigurationUseCases._build_snapshot` injects `id`/`versionId` literally); its *nested*
content mirrors whatever `version.definition_document` holds verbatim -- structurally validated
against `configuration.domain.content.FormDefinitionContent` at publish time, whose own module
docstring is the literal anchor for the shape: `fields` is a **top-level array**, sibling to
`sections`, not nested under it -- "specifically to satisfy the physical schema's own sanity-floor
CHECK (`jsonb_typeof(definition_document->'fields') = 'array'`)"; each `FormFieldContent` instead
carries its own `section_code` back-reference. `sections` exists only for rendering
order/grouping and is never consulted here.
"""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from catalog.application.ports import CatalogPlatformSettings, CategorySnapshot, FormBinding
from catalog.domain import FieldValidatorSpec

_PLATFORM_SETTINGS_CODE = "platform-settings-global"


class _CategoryReader(Protocol):
    """The narrow slice of `configuration.application.category_read.CategoryReadUseCases` this
    module actually calls."""

    async def get_category(self, category_id: UUID) -> dict[str, Any] | None: ...

    async def get_category_form(self, category_id: UUID) -> dict[str, Any] | None: ...


class _PlatformSettingsReader(Protocol):
    """The narrow slice of `configuration.interfaces.ports.ConfigurationPort` this module
    actually calls, for the `listing.default_expiry_days` setting."""

    async def list_config_heads(
        self, entity_type: str, cursor: str | None = None, limit: int | None = 20
    ) -> Any: ...

    async def get_config_version(
        self, entity_type: str, head_id: UUID, version_id: UUID
    ) -> Any: ...


def _flatten_specs(form_snapshot: dict[str, Any]) -> tuple[FieldValidatorSpec, ...]:
    """Flattens the resolved FormDefinition snapshot's top-level `fields -> validators` list
    (`configuration.domain.content.FormDefinitionContent.fields` -- NOT nested under `sections`,
    see this module's own docstring) into the flat closed-vocabulary spec list
    `catalog.domain.policies.validate_attribute_set` executes. A `required` field is guaranteed
    exactly one spec with `required_field=True` (synthesizing a `"required"`-type validator if
    the field's own configured validators do not already include one) so the "field is required"
    check never fires once per validator on the same field -- a defensible implementation choice
    where the approved documents specify the six validator types but not how a field's own
    `required` flag composes with them."""
    specs: list[FieldValidatorSpec] = []
    for field in form_snapshot.get("fields", []):
        code = field["code"]
        required = bool(field.get("required", False))
        validators: list[dict[str, Any]] = list(field.get("validators") or [])
        if required and not any(v.get("validator_type") == "required" for v in validators):
            validators = [{"validator_type": "required", "params": {}}, *validators]
        field_options = [
            str(option["value"]) for option in field.get("options") or [] if "value" in option
        ]
        for index, validator in enumerate(validators):
            params = dict(validator.get("params") or {})
            # UNF-002: `option_membership` validates against the FIELD's own configured
            # `options` list (`configuration.domain.content.FormFieldContent.options`, a
            # sibling of `validators`, never nested under a binding's own `params`) -- an
            # `option_membership` binding is always authored as `{"params": {}}` (there is
            # nowhere else to put the allowed values), so `params.get("options", [])` in
            # `catalog.domain.policies._check_option_membership` was always `[]` and every
            # select/multiselect field rejected every value the API itself served as `options`.
            if validator["validator_type"] == "option_membership" and "options" not in params:
                params["options"] = field_options
            specs.append(
                FieldValidatorSpec(
                    field_code=code,
                    validator_type=validator["validator_type"],
                    params=params,
                    required_field=required and index == 0,
                )
            )
    return tuple(specs)


class ConfigurationCategoryFormAdapter:
    """Implements `catalog.application.ports.CategoryFormPort`."""

    def __init__(self, categories: _CategoryReader) -> None:
        self._categories = categories

    async def get_category(self, category_id: UUID) -> CategorySnapshot | None:
        snapshot = await self._categories.get_category(category_id)
        if snapshot is None:
            return None
        form_id = snapshot.get("form_definition_id")
        return CategorySnapshot(
            id=category_id,
            path=str(snapshot.get("path", "")),
            status="RETIRED" if snapshot.get("tree_status") == "RETIRED" else "ACTIVE",
            form_definition_head_id=UUID(str(form_id)) if form_id else None,
        )

    async def get_current_form_binding(self, category_id: UUID) -> FormBinding | None:
        form_snapshot = await self._categories.get_category_form(category_id)
        if form_snapshot is None:
            return None
        return FormBinding(
            form_definition_id=UUID(str(form_snapshot["id"])),
            form_definition_version_id=UUID(str(form_snapshot["versionId"])),
            specs=_flatten_specs(form_snapshot),
            field_codes=frozenset(str(field["code"]) for field in form_snapshot.get("fields", [])),
        )


class ConfigurationPlatformSettingsAdapter:
    """Implements `catalog.application.ports.PlatformSettingsReaderPort` (DEC-21: never hardcode
    a configurable value). Mirrors `identity.infrastructure.configuration_adapter.
    ConfigurationPlatformSettingsAdapter`'s own head/version pagination-and-match strategy against
    the same `platform-settings-global` head (`configuration`, seeded in P-04)."""

    def __init__(self, configuration: _PlatformSettingsReader) -> None:
        self._configuration = configuration

    async def get_catalog_settings(self) -> CatalogPlatformSettings:
        cursor: str | None = None
        while True:
            page = await self._configuration.list_config_heads(
                "platform-settings", cursor=cursor, limit=50
            )
            for head in page.items:
                if head.code == _PLATFORM_SETTINGS_CODE and head.current_version_id is not None:
                    version = await self._configuration.get_config_version(
                        "platform-settings", head.id, head.current_version_id
                    )
                    settings = (version.snapshot or {}).get("settings", {})
                    return CatalogPlatformSettings(
                        default_expiry_days=int(settings["listing.default_expiry_days"])
                    )
            cursor = page.page.next_cursor
            if cursor is None:
                raise LookupError(
                    f"no published platform-settings head with code {_PLATFORM_SETTINGS_CODE!r}"
                )
