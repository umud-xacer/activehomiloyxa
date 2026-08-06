"""The eight configuration entity types and their authoring track (Config Framework Sec 2.3,
Sec 3, Sec 10; DDD Sec 5.4). One closed enum, reused everywhere `entityType` appears -- the
OpenAPI `ConfigurationHead.entityType` enum, `contracts/openapi.yaml`'s `ConfigEntityTypePath`,
and this module's own generic machinery, all read from the same eight values (Physical DB
Sec 2.4 "the eight entities share one physical pattern instantiated eight times").
"""

from __future__ import annotations

from enum import StrEnum


class ConfigEntityType(StrEnum):
    """Matches `configuration/interfaces/dto.py`'s `ConfigurationHead.entity_type` Literal
    exactly (frozen at Task P-01 from `contracts/openapi.yaml`'s `ConfigEntityTypePath`
    parameter) -- do not add or rename a member without an ADR amending the OpenAPI spec."""

    CATEGORY = "category"
    FORM_DEFINITION = "form-definition"
    PRODUCT_DEFINITION = "product-definition"
    PLACEMENT_SLOT = "placement-slot"
    ROLE_DEFINITION = "role-definition"
    SEARCH_CONFIGURATION = "search-configuration"
    NOTIFICATION_TEMPLATE = "notification-template"
    PLATFORM_SETTINGS = "platform-settings"


class AuthoringTrack(StrEnum):
    """Config Framework Sec 2.3: two authoring tracks selected by the entity's impact class.
    Standard: single-actor, author self-checks against the gate, then publishes. Controlled:
    maker (author) -> gate -> checker (a different principal) -> publish."""

    STANDARD = "STANDARD"
    CONTROLLED = "CONTROLLED"


CONTROLLED_TRACK_ENTITIES: frozenset[ConfigEntityType] = frozenset(
    {
        ConfigEntityType.CATEGORY,  # "taxonomy structure" -- CF Sec 2.3
        ConfigEntityType.FORM_DEFINITION,  # "form/validation definitions" -- CF Sec 2.3
        ConfigEntityType.PRODUCT_DEFINITION,  # "plans/prices, verification/badge terms" -- CF Sec 2.3
        ConfigEntityType.PLACEMENT_SLOT,  # "banner inventory" -- CF Sec 2.3
        ConfigEntityType.ROLE_DEFINITION,  # "role composition" -- CF Sec 2.3, Super-Admin approver
        ConfigEntityType.PLATFORM_SETTINGS,  # "platform settings" -- CF Sec 2.3, Super-Admin approver
    }
)
"""CF Sec 2.3 names these six explicitly as controlled-track ("anything that changes behaviour,
money, safety, or access"). SearchConfiguration and NotificationTemplate are not named in either
track list; NotificationTemplate is covered by the standard-track example "notification
wording", and SearchConfiguration (facet/sort selection, promotion-cap value) is treated as
standard-track by the same reasoning as the standard-track example "homepage ordering" -- a
structural/display configuration, not one that itself moves money, safety, or access. Flagged
explicitly (README) since neither document sentence names SearchConfiguration by word."""

SUPER_ADMIN_APPROVAL_ENTITIES: frozenset[ConfigEntityType] = frozenset(
    {
        ConfigEntityType.ROLE_DEFINITION,
        ConfigEntityType.PLATFORM_SETTINGS,
    }
)
"""CF Sec 2.3: "role and settings changes require Super-Administrator approval" -- narrower than
the controlled-track set. The other four controlled-track entities require a different
principal as checker, but not specifically a Super-Administrator."""


def authoring_track(entity_type: ConfigEntityType) -> AuthoringTrack:
    if entity_type in CONTROLLED_TRACK_ENTITIES:
        return AuthoringTrack.CONTROLLED
    return AuthoringTrack.STANDARD


def requires_super_admin_approval(entity_type: ConfigEntityType) -> bool:
    return entity_type in SUPER_ADMIN_APPROVAL_ENTITIES


TABLE_NAME_BY_ENTITY_TYPE: dict[ConfigEntityType, str] = {
    ConfigEntityType.CATEGORY: "category",
    ConfigEntityType.FORM_DEFINITION: "form_definition",
    ConfigEntityType.PRODUCT_DEFINITION: "product_definition",
    ConfigEntityType.PLACEMENT_SLOT: "placement_slot",
    ConfigEntityType.ROLE_DEFINITION: "role_definition",
    ConfigEntityType.SEARCH_CONFIGURATION: "search_configuration",
    ConfigEntityType.NOTIFICATION_TEMPLATE: "notification_template",
    ConfigEntityType.PLATFORM_SETTINGS: "platform_settings",
}
"""Physical DB Sec 2.4 table names (`configuration.<entity>` / `configuration.<entity>_version`)
use snake_case; the API's `entityType` path segment (above) uses kebab-case. This is the one
translation point between the two, kept in a single dict rather than a naming convention so a
mismatch is a `KeyError`, not a silent divergence."""
