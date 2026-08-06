"""Maps a publish outcome to its `ConfigurationChanged` specialisation event_type (Config
Framework Sec 2.4: "BC-04 emits the corresponding ConfigurationChanged specialisation"; the
exact eleven event_type literals are frozen in `contracts/events/configuration.py`, Task P-01).
Only Category has three specialisations (Created/Changed/Retired); the other seven entities
each have exactly one, fired on every publish regardless of whether it is that head's first
version. Returns a plain string, not an `EventEnvelope` -- constructing the envelope needs
aggregate ids/actor/payload assembled by the calling use case (`application/`), and importing
`contracts.events` itself is an `interfaces/`/`infrastructure/` concern, not `domain/`'s
(Clean Architecture rule 1 restricts `domain/` to `shared_kernel` only).
"""

from __future__ import annotations

from configuration.domain.entity_types import ConfigEntityType

_SINGLE_EVENT_TYPE_BY_ENTITY: dict[ConfigEntityType, str] = {
    ConfigEntityType.FORM_DEFINITION: "FormDefinitionPublished",
    ConfigEntityType.PRODUCT_DEFINITION: "ProductDefinitionChanged",
    ConfigEntityType.PLACEMENT_SLOT: "PlacementSlotDefined",
    ConfigEntityType.ROLE_DEFINITION: "RoleDefinitionChanged",
    ConfigEntityType.SEARCH_CONFIGURATION: "SearchConfigurationChanged",
    ConfigEntityType.NOTIFICATION_TEMPLATE: "NotificationTemplateChanged",
    ConfigEntityType.PLATFORM_SETTINGS: "PlatformSettingsChanged",
}


def resolve_configuration_changed_event_type(
    entity_type: ConfigEntityType, *, is_new_head: bool, category_tree_status: str | None = None
) -> str:
    if entity_type == ConfigEntityType.CATEGORY:
        if category_tree_status == "RETIRED":
            return "CategoryRetired"
        return "CategoryCreated" if is_new_head else "CategoryChanged"
    return _SINGLE_EVENT_TYPE_BY_ENTITY[entity_type]
