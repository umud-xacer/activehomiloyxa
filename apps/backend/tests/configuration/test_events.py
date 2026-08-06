"""`resolve_configuration_changed_event_type` -- maps a publish outcome to its
`ConfigurationChanged` specialisation event_type (Config Framework Sec 2.4; frozen literals in
`contracts/events/configuration.py`, Task P-01)."""

from __future__ import annotations

import pytest

from configuration.domain.entity_types import ConfigEntityType
from configuration.domain.events import resolve_configuration_changed_event_type


def test_category_new_head_is_created() -> None:
    assert (
        resolve_configuration_changed_event_type(
            ConfigEntityType.CATEGORY, is_new_head=True, category_tree_status="ACTIVE"
        )
        == "CategoryCreated"
    )


def test_category_existing_head_republish_is_changed() -> None:
    assert (
        resolve_configuration_changed_event_type(
            ConfigEntityType.CATEGORY, is_new_head=False, category_tree_status="ACTIVE"
        )
        == "CategoryChanged"
    )


def test_category_retired_wins_regardless_of_new_head() -> None:
    assert (
        resolve_configuration_changed_event_type(
            ConfigEntityType.CATEGORY, is_new_head=False, category_tree_status="RETIRED"
        )
        == "CategoryRetired"
    )
    assert (
        resolve_configuration_changed_event_type(
            ConfigEntityType.CATEGORY, is_new_head=True, category_tree_status="RETIRED"
        )
        == "CategoryRetired"
    )


@pytest.mark.parametrize(
    "entity_type,expected",
    [
        (ConfigEntityType.FORM_DEFINITION, "FormDefinitionPublished"),
        (ConfigEntityType.PRODUCT_DEFINITION, "ProductDefinitionChanged"),
        (ConfigEntityType.PLACEMENT_SLOT, "PlacementSlotDefined"),
        (ConfigEntityType.ROLE_DEFINITION, "RoleDefinitionChanged"),
        (ConfigEntityType.SEARCH_CONFIGURATION, "SearchConfigurationChanged"),
        (ConfigEntityType.NOTIFICATION_TEMPLATE, "NotificationTemplateChanged"),
        (ConfigEntityType.PLATFORM_SETTINGS, "PlatformSettingsChanged"),
    ],
)
def test_non_category_entities_have_exactly_one_specialisation(
    entity_type: ConfigEntityType, expected: str
) -> None:
    assert resolve_configuration_changed_event_type(entity_type, is_new_head=True) == expected
    assert resolve_configuration_changed_event_type(entity_type, is_new_head=False) == expected


def test_every_resolved_event_type_is_whitelisted() -> None:
    from configuration.domain.whitelist import WhitelistRegistry

    registry = WhitelistRegistry()
    for entity_type in ConfigEntityType:
        for is_new_head in (True, False):
            for tree_status in ("ACTIVE", "RETIRED"):
                event_type = resolve_configuration_changed_event_type(
                    entity_type,
                    is_new_head=is_new_head,
                    category_tree_status=tree_status,
                )
                registry.check_event_key(event_type)  # does not raise
