"""The pre-activation validation gate (Config Framework Sec 9; I-16). One generic evaluator,
dispatching to small per-entity check functions declared in `_ENTITY_CHECKS` -- the "generic
machinery instantiated eight times" pattern applied to validation, not just persistence.

Pure domain policy: takes already-fetched facts (`GateContext`) and already-parsed content
(`domain.content`), returns a `GateResult` -- never raises for a business-rule failure (that
would collapse "which checks failed" into one exception) and never does I/O itself (Clean
Architecture rule 1). The calling use case (`application/`) gathers `GateContext` via repository
ports, calls `PreActivationGate.evaluate(...)`, and turns a non-empty result into either an API
`ConfigValidationResult` (dry run) or a refused publish (real run) -- same gate, same code path,
matching Config Framework Sec 9 "mandatory for both the standard and controlled tracks ... and
for rollback".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import ValidationError

from configuration.domain.content import (
    CONTENT_MODEL_BY_ENTITY_TYPE,
    CategoryContent,
    FormDefinitionContent,
    NotificationTemplateContent,
    PlacementSlotContent,
    PlatformSettingsContent,
    ProductDefinitionContent,
    RoleDefinitionContent,
    SearchConfigurationContent,
)
from configuration.domain.taxonomy import creates_cycle, would_orphan_listings
from configuration.domain.whitelist import WhitelistRegistry


@dataclass(frozen=True)
class GateError:
    code: str
    message: str
    field: str | None = None


@dataclass(frozen=True)
class GateResult:
    errors: tuple[GateError, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.errors


def _structure_errors(exc: ValidationError) -> list[GateError]:
    """One `GateError` per underlying pydantic error, each naming its own field.

    `str(ValidationError)` was being used as a single message, which put this in front of an
    administrator:

        1 validation error for CategoryContent
        form_definition_id Input should be a valid UUID, invalid character: found `n` at 1
        [type=uuid_parsing, input_value='not-a-uuid', input_type=str]
        For further information visit https://errors.pydantic.dev/2.13/v/uuid_parsing

    -- the internal model class name, a machine error code, and a link to a Python library's
    documentation, all for a mistyped id, and attached to path "/" so the editor could not point
    at the field. Expanding `exc.errors()` gives the shape `GateError` already has room for
    (`field` is mapped to `ValidationError.path` by `interfaces/routers`), so the operator gets
    one line per problem naming the field they can actually go and fix.

    `msg` alone is deliberately what carries through: pydantic's own wording ("Field required",
    "Input should be a valid UUID") is already plain, while `type`/`input`/`url` are for whoever
    is reading a stack trace, not for whoever is authoring a category.
    """
    errors: list[GateError] = []
    for detail in exc.errors():
        location: tuple[Any, ...] = detail.get("loc", ())
        # `loc` mixes field names and list indices; dots read better than a tuple, and an empty
        # `loc` (a whole-document failure) keeps `field=None` so the router still emits "/".
        field_path = ".".join(str(part) for part in location) or None
        errors.append(
            GateError("INVALID_STRUCTURE", str(detail.get("msg", "invalid value")), field_path)
        )
    return errors or [GateError("INVALID_STRUCTURE", "invalid definition document")]


@dataclass(frozen=True)
class GateContext:
    """Facts the gate needs but cannot fetch itself -- gathered by the calling use case via
    repository/lookup ports before invoking the gate (Clean Architecture rule 1)."""

    entity_type: str
    existing_codes: frozenset[str] = field(default_factory=frozenset)
    """Other heads' codes for this entity type (duplicate-code check), excluding this head's own
    code when re-validating an existing head's new draft."""
    dependency_exists: dict[str, bool] = field(default_factory=dict)
    """`"<kind>:<reference>"` -> whether that dependency exists and is publishable."""
    category_has_bound_listings: bool = False
    """I-03: only meaningful when validating a Category transitioning to RETIRED."""
    ancestor_codes_of_parent: frozenset[str] = field(default_factory=frozenset)
    """Category cycle check: codes of the proposed parent and all of its ancestors."""
    ancestor_codes_of_parent_role: frozenset[str] = field(default_factory=frozenset)
    """RoleDefinition cycle check: codes of the proposed parent role and all of its ancestors."""
    validity_from: datetime | None = None
    validity_until: datetime | None = None
    conflicting_active_version_exists: bool = False
    """Config Framework Sec 4: "a validity window that conflicts with an existing active
    version"."""


def _check_translations(
    descriptor_name_present_locales: frozenset[str], field_label: str
) -> list[GateError]:
    if "uz_latn" not in descriptor_name_present_locales:
        return [
            GateError(
                "MISSING_TRANSLATION",
                f"{field_label} is missing the required uz_latn translation",
                field=field_label,
            )
        ]
    return []


def _present_locales(text: object) -> frozenset[str]:
    locales = set()
    for locale in ("uz_latn", "uz_cyrl", "ru", "en"):
        if getattr(text, locale, None):
            locales.add(locale)
    return frozenset(locales)


def _check_category(
    code: str, content: CategoryContent, ctx: GateContext, whitelist: WhitelistRegistry
) -> list[GateError]:
    errors: list[GateError] = []
    errors.extend(_check_translations(_present_locales(content.descriptor.name), "descriptor.name"))
    key = f"form-definition:{content.form_definition_id}"
    if not ctx.dependency_exists.get(key, False):
        errors.append(
            GateError(
                "MISSING_DEPENDENCY",
                f"bound form {content.form_definition_id} does not exist or is not publishable",
                field="form_definition_id",
            )
        )
    if content.parent_category_id is not None and creates_cycle(code, ctx.ancestor_codes_of_parent):
        errors.append(
            GateError(
                "CIRCULAR_REFERENCE",
                f"category tree cycle detected: {code!r} is its own ancestor via the proposed parent",
                field="parent_category_id",
            )
        )
    if would_orphan_listings(content.tree_status, ctx.category_has_bound_listings):
        errors.append(
            GateError(
                "ORPHANED_LISTINGS",
                "retiring this category would orphan bound listings without a remap",
            )
        )
    return errors


def _check_form_definition(
    code: str,
    content: FormDefinitionContent,
    ctx: GateContext,
    whitelist: WhitelistRegistry,
) -> list[GateError]:
    errors: list[GateError] = []
    errors.extend(_check_translations(_present_locales(content.descriptor.name), "descriptor.name"))
    section_codes = {section.code for section in content.sections}
    seen_field_codes: set[str] = set()
    for f in content.fields:
        if f.code in seen_field_codes:
            errors.append(
                GateError(
                    "DUPLICATE_FIELD_CODE",
                    f"field code {f.code!r} repeated",
                    field="fields",
                )
            )
        seen_field_codes.add(f.code)
        try:
            whitelist.check_field_type(f.field_type)
        except ValueError as exc:
            errors.append(
                GateError("WHITELIST_VIOLATION", str(exc), field=f"fields.{f.code}.field_type")
            )
        if f.section_code not in section_codes:
            errors.append(
                GateError(
                    "MISSING_DEPENDENCY",
                    f"field {f.code!r} references unknown section {f.section_code!r}",
                    field=f"fields.{f.code}.section_code",
                )
            )
        for validator in f.validators:
            try:
                whitelist.check_validator_type(validator.validator_type)
            except ValueError as exc:
                errors.append(
                    GateError(
                        "WHITELIST_VIOLATION",
                        str(exc),
                        field=f"fields.{f.code}.validators",
                    )
                )
            if validator.validator_type == "pattern_safe":
                pattern = validator.params.get("pattern_key")
                if not isinstance(pattern, str) or not pattern:
                    errors.append(
                        GateError(
                            "UNSAFE_CONTENT",
                            "pattern_safe validator requires a safe pattern_key parameter, not an arbitrary regex",
                            field=f"fields.{f.code}.validators",
                        )
                    )
        if f.conditional_visibility is not None:
            try:
                whitelist.check_condition_operator(f.conditional_visibility.operator)
            except ValueError as exc:
                errors.append(
                    GateError(
                        "WHITELIST_VIOLATION",
                        str(exc),
                        field=f"fields.{f.code}.conditional_visibility",
                    )
                )
            if (
                f.conditional_visibility.field_code not in seen_field_codes
                and f.conditional_visibility.field_code
                not in {other.code for other in content.fields}
            ):
                errors.append(
                    GateError(
                        "MISSING_DEPENDENCY",
                        f"conditional visibility references unknown field {f.conditional_visibility.field_code!r}",
                        field=f"fields.{f.code}.conditional_visibility",
                    )
                )
        if f.rendering_hint is not None:
            try:
                whitelist.check_rendering_hint(f.rendering_hint)
            except ValueError as exc:
                errors.append(
                    GateError(
                        "WHITELIST_VIOLATION",
                        str(exc),
                        field=f"fields.{f.code}.rendering_hint",
                    )
                )
    return errors


def _check_product_definition(
    code: str,
    content: ProductDefinitionContent,
    ctx: GateContext,
    whitelist: WhitelistRegistry,
) -> list[GateError]:
    errors: list[GateError] = []
    errors.extend(_check_translations(_present_locales(content.descriptor.name), "descriptor.name"))
    try:
        whitelist.check_product_type(content.product_type)
    except ValueError as exc:
        errors.append(GateError("WHITELIST_VIOLATION", str(exc), field="product_type"))
    if content.price_amount < 0:
        errors.append(
            GateError(
                "CONFLICTING_RULE",
                "price_amount must not be negative",
                field="price_amount",
            )
        )
    return errors


def _check_placement_slot(
    code: str,
    content: PlacementSlotContent,
    ctx: GateContext,
    whitelist: WhitelistRegistry,
) -> list[GateError]:
    errors: list[GateError] = []
    errors.extend(_check_translations(_present_locales(content.descriptor.name), "descriptor.name"))
    try:
        whitelist.check_page_zone(content.page_zone)
    except ValueError as exc:
        errors.append(GateError("WHITELIST_VIOLATION", str(exc), field="page_zone"))
    return errors


def _check_role_definition(
    code: str,
    content: RoleDefinitionContent,
    ctx: GateContext,
    whitelist: WhitelistRegistry,
) -> list[GateError]:
    errors: list[GateError] = []
    for key in content.permission_keys:
        try:
            whitelist.check_permission_key(key)
        except ValueError as exc:
            errors.append(GateError("WHITELIST_VIOLATION", str(exc), field="permission_keys"))
    for group_code in content.permission_group_codes:
        group_key = f"permission-group:{group_code}"
        if not ctx.dependency_exists.get(group_key, False):
            errors.append(
                GateError(
                    "MISSING_DEPENDENCY",
                    f"permission group {group_code!r} does not exist",
                    field="permission_group_codes",
                )
            )
    if content.parent_role_code is not None:
        parent_key = f"role-definition:{content.parent_role_code}"
        if not ctx.dependency_exists.get(parent_key, False):
            errors.append(
                GateError(
                    "MISSING_DEPENDENCY",
                    f"parent role {content.parent_role_code!r} does not exist or is not publishable",
                    field="parent_role_code",
                )
            )
        if creates_cycle(code, ctx.ancestor_codes_of_parent_role):
            errors.append(
                GateError(
                    "CIRCULAR_REFERENCE",
                    f"role hierarchy cycle detected via {content.parent_role_code!r}",
                    field="parent_role_code",
                )
            )
    if (
        not content.permission_keys
        and not content.permission_group_codes
        and content.parent_role_code is None
    ):
        errors.append(
            GateError(
                "CONFLICTING_RULE",
                "a role must carry at least one permission (directly, via a group, or via a parent role)",
                field="permission_keys",
            )
        )
    return errors


def _check_search_configuration(
    code: str,
    content: SearchConfigurationContent,
    ctx: GateContext,
    whitelist: WhitelistRegistry,
) -> list[GateError]:
    errors: list[GateError] = []
    for option in content.sort_options:
        try:
            whitelist.check_sort_option(option)
        except ValueError as exc:
            errors.append(GateError("WHITELIST_VIOLATION", str(exc), field="sort_options"))
    if content.default_sort not in content.sort_options:
        errors.append(
            GateError(
                "CONFLICTING_RULE",
                "default_sort must be one of the enabled sort_options",
                field="default_sort",
            )
        )
    if content.promotion_page_cap < 0:
        errors.append(
            GateError(
                "CONFLICTING_RULE",
                "promotion_page_cap must not be negative",
                field="promotion_page_cap",
            )
        )
    for facet in content.facets:
        key = f"facet-eligible-field:{facet.field_code}"
        if not ctx.dependency_exists.get(key, True):
            errors.append(
                GateError(
                    "MISSING_DEPENDENCY",
                    f"facet references a field not marked facet-eligible: {facet.field_code!r}",
                    field="facets",
                )
            )
    return errors


def _check_notification_template(
    code: str,
    content: NotificationTemplateContent,
    ctx: GateContext,
    whitelist: WhitelistRegistry,
) -> list[GateError]:
    errors: list[GateError] = []
    try:
        whitelist.check_event_key(content.event_key)
    except ValueError as exc:
        errors.append(GateError("WHITELIST_VIOLATION", str(exc), field="event_key"))
    try:
        whitelist.check_notification_channel(content.channel)
    except ValueError as exc:
        errors.append(GateError("WHITELIST_VIOLATION", str(exc), field="channel"))
    errors.extend(_check_translations(_present_locales(content.subject), "subject"))
    errors.extend(_check_translations(_present_locales(content.body), "body"))
    return errors


def _check_platform_settings(
    code: str,
    content: PlatformSettingsContent,
    ctx: GateContext,
    whitelist: WhitelistRegistry,
) -> list[GateError]:
    errors: list[GateError] = []
    for key, value in content.settings.items():
        try:
            whitelist.check_settings_key(key, value)
        except ValueError as exc:
            errors.append(GateError("WHITELIST_VIOLATION", str(exc), field=f"settings.{key}"))
    for zone in content.homepage_zones:
        try:
            whitelist.check_page_zone(zone.zone)
        except ValueError as exc:
            errors.append(GateError("WHITELIST_VIOLATION", str(exc), field="homepage_zones"))
    for template in content.seo_templates:
        try:
            whitelist.check_seo_page_type(template.page_type)
        except ValueError as exc:
            errors.append(GateError("WHITELIST_VIOLATION", str(exc), field="seo_templates"))
        errors.extend(
            _check_translations(
                _present_locales(template.title),
                f"seo_templates[{template.page_type}].title",
            )
        )
    for page in content.static_pages:
        try:
            whitelist.check_static_page_key(page.page_key)
        except ValueError as exc:
            errors.append(GateError("WHITELIST_VIOLATION", str(exc), field="static_pages"))
        errors.extend(
            _check_translations(_present_locales(page.body), f"static_pages[{page.page_key}].body")
        )
    return errors


_ENTITY_CHECKS: dict[str, object] = {
    "category": _check_category,
    "form-definition": _check_form_definition,
    "product-definition": _check_product_definition,
    "placement-slot": _check_placement_slot,
    "role-definition": _check_role_definition,
    "search-configuration": _check_search_configuration,
    "notification-template": _check_notification_template,
    "platform-settings": _check_platform_settings,
}


class PreActivationGate:
    """Config Framework Sec 9: whitelist membership, dependencies, cycles, translations, dates,
    duplicate codes, conflicting rules, and safety -- run before Draft/edited content may become
    Current, on both authoring tracks, and again on rollback (Sec 2.6)."""

    def __init__(self, whitelist: WhitelistRegistry | None = None) -> None:
        self._whitelist = whitelist or WhitelistRegistry()

    def evaluate(
        self,
        entity_type: str,
        code: str,
        raw_content: dict[str, object],
        ctx: GateContext,
    ) -> GateResult:
        errors: list[GateError] = []

        if code in ctx.existing_codes:
            errors.append(
                GateError(
                    "DUPLICATE_CODE",
                    f"code {code!r} already exists for entity type {entity_type!r}",
                    field="code",
                )
            )

        if (
            ctx.validity_from is not None
            and ctx.validity_until is not None
            and ctx.validity_until <= ctx.validity_from
        ):
            errors.append(
                GateError(
                    "INVALID_VALIDITY_PERIOD",
                    "validity_until must be strictly after validity_from",
                    field="validityUntil",
                )
            )
        if ctx.conflicting_active_version_exists:
            errors.append(
                GateError(
                    "INVALID_VALIDITY_PERIOD",
                    "validity window conflicts with an existing active version",
                    field="validityFrom",
                )
            )

        content_model_type = CONTENT_MODEL_BY_ENTITY_TYPE.get(entity_type)
        if content_model_type is None:
            errors.append(
                GateError(
                    "UNKNOWN_ENTITY_TYPE",
                    f"no content model registered for {entity_type!r}",
                )
            )
            return GateResult(tuple(errors))

        try:
            content = content_model_type.model_validate(raw_content)
        except ValidationError as exc:
            errors.extend(_structure_errors(exc))
            return GateResult(tuple(errors))
        except Exception as exc:  # non-pydantic failure -- keep the raw text rather than lose it
            errors.append(GateError("INVALID_STRUCTURE", str(exc)))
            return GateResult(tuple(errors))

        check_fn = _ENTITY_CHECKS[entity_type]
        errors.extend(check_fn(code, content, ctx, self._whitelist))  # type: ignore[operator]

        return GateResult(tuple(errors))
