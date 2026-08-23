"""Per-entity `definition_document` content models (Physical DB Sec 2.4 "complete self-contained
Configuration Descriptor + entity structure"; Config Framework Sec 4 Configuration Descriptor +
Sec 3 catalogue). Structural/type validation only (Pydantic); whitelist membership and
cross-entity business rules are the gate's job (`gate.py`), not these models'.

Each model's shape mirrors the Physical DB Sec 2.4 "per-entity promoted columns" table exactly
-- those columns are extracted *from* `definition_document` at publish, so the document must
carry them. `FormDefinitionContent.fields` is a top-level array (not nested under `sections`)
specifically to satisfy the physical schema's own sanity-floor CHECK
(`jsonb_typeof(definition_document->'fields') = 'array'`); `sections` groups fields by code for
rendering order, reconciling that CHECK with Config Framework Sec 5.1's Sections-then-Fields
description.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from shared_kernel import LocalizedText

_ConfigContentModel = BaseModel


class ConfigDescriptor(_ConfigContentModel):
    """Config Framework Sec 4 -- the common metadata envelope embedded in every entity's
    content, alongside its entity-specific fields (Sec 4 "Recommended reuse pattern")."""

    model_config = ConfigDict(extra="forbid")

    name: LocalizedText
    description: LocalizedText | None = None
    display_order: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    """Bounded key-value extension slot -- inert data only, cannot encode logic (I-16)."""


class CategoryContent(_ConfigContentModel):
    model_config = ConfigDict(extra="forbid")

    descriptor: ConfigDescriptor
    parent_category_id: UUID | None = None
    path: str
    form_definition_id: UUID
    """Exactly one binding (I-02)."""
    tree_status: Literal["ACTIVE", "RETIRED"] = "ACTIVE"


class FormFieldOption(_ConfigContentModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    label: LocalizedText


class ConditionalVisibility(_ConfigContentModel):
    model_config = ConfigDict(extra="forbid")

    field_code: str
    operator: Literal[
        "EQUALS", "NOT_EQUALS", "IN", "NOT_IN", "GREATER_THAN", "LESS_THAN"
    ]
    value: Any = None


class ValidatorBindingContent(_ConfigContentModel):
    model_config = ConfigDict(extra="forbid")

    validator_type: str
    params: dict[str, Any] = Field(default_factory=dict)


class FormFieldContent(_ConfigContentModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    section_code: str
    label: LocalizedText
    field_type: str
    required: bool = False
    facet_eligible: bool = False
    order: int = 0
    default_value: Any = None
    options: list[FormFieldOption] = Field(default_factory=list)
    validators: list[ValidatorBindingContent] = Field(default_factory=list)
    rendering_hint: str | None = None
    conditional_visibility: ConditionalVisibility | None = None


class FormSectionContent(_ConfigContentModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    label: LocalizedText
    order: int = 0


class FormDefinitionContent(_ConfigContentModel):
    """No `category_id` field: Physical DB Sec 2.4's Extra-columns table lists no promoted
    columns for `form_definition`/`_version` at all -- the binding is one-directional,
    `category.form_definition_id` (NOT NULL, I-02 "exactly one binding"); a form does not name
    the category(ies) that reference it, so a form can be authored and published standalone,
    before any category exists to bind it."""

    model_config = ConfigDict(extra="forbid")

    descriptor: ConfigDescriptor
    sections: list[FormSectionContent]
    fields: list[FormFieldContent]


class QuotaSetContent(_ConfigContentModel):
    model_config = ConfigDict(extra="forbid")

    max_active_listings: int | None = None
    promotion_credits: int | None = None
    listing_publish_credits: int | None = None
    """`LISTING_CREDIT_PACK` products only (2026-08-23, listing paywall): how many future
    listing publishes this pack grants. `unlimited_listing_publish=True` overrides this (the
    Unlim/Premium tier)."""
    unlimited_listing_publish: bool | None = None


class ProductDefinitionContent(_ConfigContentModel):
    model_config = ConfigDict(extra="forbid")

    descriptor: ConfigDescriptor
    product_type: str
    price_amount: Decimal
    price_currency: str = "UZS"
    term_days: int | None = None
    quota_set: QuotaSetContent | None = None
    benefit_descriptor: dict[str, Any] = Field(default_factory=dict)
    category_id: UUID | None = None
    """`LISTING_PUBLICATION` products only (2026-08-23, listing paywall): a category-specific
    override price. `None` = the platform-default single-listing price (the row with no
    `category_id` set for this product type)."""


class PlacementSlotContent(_ConfigContentModel):
    model_config = ConfigDict(extra="forbid")

    descriptor: ConfigDescriptor
    slot_key: str
    page_zone: str
    width_px: int | None = None
    height_px: int | None = None
    targeting_dimensions: list[str] = Field(default_factory=list)


class RoleDefinitionContent(_ConfigContentModel):
    model_config = ConfigDict(extra="forbid")

    descriptor: ConfigDescriptor
    role_name: str
    permission_keys: list[str] = Field(default_factory=list)
    """Directly selected catalogue keys (Config Framework Sec 7.1)."""
    permission_group_codes: list[str] = Field(default_factory=list)
    """Authoring-time convenience, expanded at publish (Physical DB Sec 2.4 `permission_group`)."""
    parent_role_code: str | None = None
    """Authoring-time role-hierarchy composition, flattened at publish; no runtime inheritance
    (Config Framework Sec 7.1)."""


class FacetContent(_ConfigContentModel):
    model_config = ConfigDict(extra="forbid")

    field_code: str
    label: LocalizedText
    order: int = 0


class SearchConfigurationContent(_ConfigContentModel):
    model_config = ConfigDict(extra="forbid")

    descriptor: ConfigDescriptor
    scope_category_id: UUID | None = None
    """Null = global scope."""
    facets: list[FacetContent] = Field(default_factory=list)
    sort_options: list[str] = Field(default_factory=list)
    default_sort: str
    promotion_page_cap: int


class NotificationTemplateContent(_ConfigContentModel):
    model_config = ConfigDict(extra="forbid")

    descriptor: ConfigDescriptor
    event_key: str
    channel: str
    subject: LocalizedText
    body: LocalizedText


class HomepageZoneContent(_ConfigContentModel):
    model_config = ConfigDict(extra="forbid")

    zone: str
    order: int = 0
    reference: str | None = None


class NavigationItemContent(_ConfigContentModel):
    model_config = ConfigDict(extra="forbid")

    label: LocalizedText
    target_type: Literal["CATEGORY", "STATIC_PAGE", "SETTINGS_URL"]
    target_ref: str
    order: int = 0


class SeoTemplateContent(_ConfigContentModel):
    model_config = ConfigDict(extra="forbid")

    page_type: str
    title: LocalizedText
    meta_description: LocalizedText | None = None
    canonical: str | None = None


class StaticPageContent(_ConfigContentModel):
    model_config = ConfigDict(extra="forbid")

    page_key: str
    body: LocalizedText


class PlatformSettingsContent(_ConfigContentModel):
    """Physical DB Sec 2.4: "SEO templates, static pages, navigation, homepage layout, feature
    flags, and type-presentation are keyed sub-documents inside definition_document -- never
    separate tables" (Config Framework Sec 3.14-3.17, DEC-20/BRULE-19 no general CMS)."""

    model_config = ConfigDict(extra="forbid")

    descriptor: ConfigDescriptor
    settings_scope: str = "GLOBAL"
    settings: dict[str, Any] = Field(default_factory=dict)
    homepage_zones: list[HomepageZoneContent] = Field(default_factory=list)
    navigation_items: list[NavigationItemContent] = Field(default_factory=list)
    seo_templates: list[SeoTemplateContent] = Field(default_factory=list)
    static_pages: list[StaticPageContent] = Field(default_factory=list)


CONTENT_MODEL_BY_ENTITY_TYPE: dict[str, type[_ConfigContentModel]] = {
    "category": CategoryContent,
    "form-definition": FormDefinitionContent,
    "product-definition": ProductDefinitionContent,
    "placement-slot": PlacementSlotContent,
    "role-definition": RoleDefinitionContent,
    "search-configuration": SearchConfigurationContent,
    "notification-template": NotificationTemplateContent,
    "platform-settings": PlatformSettingsContent,
}
