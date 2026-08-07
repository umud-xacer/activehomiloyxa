"""configuration -- DTOs (Task P-01). Translated field-for-field from the OpenAPI
operations tagged to this module (contracts/openapi.yaml). Schema only: no aggregate
type is exposed here, no business behaviour, no validation beyond what Pydantic
itself does structurally.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from active_home_shared import CamelModel
from contracts.errors import Problem, ValidationError  # noqa: F401  (re-exported for ports.py)
from shared_kernel import LocalizedText


class PageInfo(CamelModel):
    """Cursor pagination metadata (OpenAPI `CursorPage.page`)."""

    limit: int
    next_cursor: str | None = None
    """Pass as `cursor` to fetch the next page; null when exhausted."""
    total: int | None = None
    """Present only where cheap to compute; may be null."""


class ConfigurationDraftRequest(CamelModel):
    """Create or edit a draft version's definition document (validated at publish)."""

    code: str | None = None
    """Required when creating a new head."""
    business_owner: str | None = None
    definition: dict[str, Any]


class ConfigurationVersion(CamelModel):
    """An immutable-once-published configuration version carrying a self-contained definition
    document."""

    id: UUID
    head_id: UUID
    version_number: int
    status: Literal["DRAFT", "VALIDATION", "APPROVAL", "PUBLISHED", "DEPRECATED", "ARCHIVED"]
    definition: dict[str, Any]
    """Complete self-contained Configuration Descriptor + entity structure."""
    snapshot: dict[str, Any] | None = None
    """Resolved consumer-facing snapshot (written at publish)."""
    validity_from: datetime | None = None
    validity_until: datetime | None = None
    rollback_of_version_id: UUID | None = None
    approved_by: UUID | None = None
    published_at: datetime | None = None


class Category(CamelModel):
    """A navigable taxonomy node (read projection of the configured Category)."""

    id: UUID
    parent_id: UUID | None = None
    name: LocalizedText
    path: str
    """Materialised path for subtree navigation."""
    slug: str | None = None
    display_order: int | None = None
    form_definition_id: UUID | None = None
    """The one bound form (I-02)."""
    status: Literal["ACTIVE", "RETIRED"] | None = None
    icon_url: str | None = None
    """Additive field (not in the original contract's `required`): a public media URL for the
    category's icon, sourced from `descriptor.metadata.iconUrl` when the admin has uploaded one.
    Optional and nullable so every pre-existing category (no icon set) round-trips unchanged."""
    hero_image_url: str | None = None
    """Additive field, same pattern as `icon_url`: sourced from `descriptor.metadata.heroImageUrl`.
    Lets the category page's Hero section be admin-authored per category instead of hardcoded."""
    hero_tagline: str | None = None
    """Additive field, sourced from `descriptor.metadata.heroTagline`."""
    accent_color: str | None = None
    """Additive field, sourced from `descriptor.metadata.accentColor`."""
    listing_kind: str | None = None
    """Additive field, sourced from `descriptor.metadata.listingKind`. Deliberately untyped (not a
    `Literal`) so a stray/legacy metadata value on any one category can never turn into a 500 for
    the whole `listCategories()` response -- the frontend validates/falls back to PROPERTY itself.
    Replaces the frontend's former hardcoded path->kind lookup table."""


class FormDefinition(CamelModel):
    """The resolved dynamic form for a category (sections → fields → validators), delivered as
    data."""

    id: UUID
    version_id: UUID
    """Immutable version bound by listings (I-07)."""
    category_id: UUID | None = None
    sections: list[FormSection]


class FormSection(CamelModel):
    """OpenAPI `FormSection`."""

    code: str
    label: LocalizedText
    order: int | None = None
    fields: list[FormField]


class FormField(CamelModel):
    """A field composed from a whitelisted field type with validation metadata and conditional
    visibility."""

    code: str
    """Key used in the listing AttributeMap."""
    label: LocalizedText
    field_type: Literal[
        "text", "number", "select", "multiselect", "boolean", "date", "range", "location", "file"
    ]
    """Whitelisted field type (closed [P] set)."""
    required: bool
    facet_eligible: bool | None = None
    """May be selected as a search facet."""
    order: int | None = None
    default_value: Any = None
    options: list[FormFieldOptions] | None = None
    """For select/multiselect."""
    validators: list[ValidatorBinding] | None = None
    rendering_hint: str | None = None
    conditional_visibility: FormFieldConditionalVisibility | None = None
    """Bounded declarative show/hide based on another field's value."""


class FormFieldOptions(CamelModel):
    """OpenAPI `FormFieldOptions`."""

    value: str | None = None
    label: LocalizedText | None = None


class ValidatorBinding(CamelModel):
    """OpenAPI `ValidatorBinding`."""

    validator_type: Literal[
        "required", "length", "numeric_range", "pattern_safe", "option_membership", "image_count"
    ]
    """Whitelisted validator (closed [P] set); pattern draws only from a safe set."""
    params: dict[str, Any] | None = None
    """Bounded parameters for the validator."""


class FormFieldConditionalVisibility(CamelModel):
    """Bounded declarative show/hide based on another field's value."""

    field_code: str | None = None
    operator: (
        Literal["EQUALS", "NOT_EQUALS", "IN", "NOT_IN", "GREATER_THAN", "LESS_THAN"] | None
    ) = None
    value: Any = None


class ConfigurationHead(CamelModel):
    """The head record of a configuration entity (uniform Head+Version pattern, DM-03)."""

    id: UUID
    entity_type: Literal[
        "category",
        "form-definition",
        "product-definition",
        "placement-slot",
        "role-definition",
        "search-configuration",
        "notification-template",
        "platform-settings",
    ]
    code: str
    """Immutable business key, unique per entity type."""
    current_version_id: UUID | None = None
    status: Literal["DRAFT", "PUBLISHED", "DEPRECATED", "ARCHIVED"]
    business_owner: str | None = None
    created_at: datetime | None = None


class ImportConfigBody(CamelModel):
    """OpenAPI `ImportConfigBody`."""

    definition: dict[str, Any]


class ConfigurationHeadPage(CamelModel):
    """A cursor-paginated page of `ConfigurationHead` (OpenAPI `CursorPage` composed with
    `items: ConfigurationHead[]` via `allOf`)."""

    items: list[ConfigurationHead]
    page: PageInfo


class ConfigPublishRequest(CamelModel):
    """OpenAPI `ConfigPublishRequest`."""

    approval_note: str | None = None
    """Recorded on the maker-checker approval (controlled track)."""


class ConfigRollbackRequest(CamelModel):
    """OpenAPI `ConfigRollbackRequest`."""

    target_version_id: UUID
    """The prior version whose content is re-published as a new version."""
    expedited: bool | None = False
    """Emergency rollback (audited)."""


class ConfigValidationResult(CamelModel):
    """Result of the pre-activation validation gate (dry-run or on publish)."""

    valid: bool
    errors: list[ValidationError] | None = None
