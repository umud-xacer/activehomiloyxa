from __future__ import annotations

from configuration.domain.entity_types import (
    CONTROLLED_TRACK_ENTITIES,
    SUPER_ADMIN_APPROVAL_ENTITIES,
    TABLE_NAME_BY_ENTITY_TYPE,
    AuthoringTrack,
    ConfigEntityType,
    authoring_track,
    requires_super_admin_approval,
)


def test_eight_entity_types_exactly() -> None:
    assert len(list(ConfigEntityType)) == 8


def test_controlled_track_is_the_six_named_by_config_framework_sec_2_3() -> None:
    assert {
        ConfigEntityType.CATEGORY,
        ConfigEntityType.FORM_DEFINITION,
        ConfigEntityType.PRODUCT_DEFINITION,
        ConfigEntityType.PLACEMENT_SLOT,
        ConfigEntityType.ROLE_DEFINITION,
        ConfigEntityType.PLATFORM_SETTINGS,
    } == CONTROLLED_TRACK_ENTITIES


def test_standard_track_is_the_remaining_two() -> None:
    standard = set(ConfigEntityType) - CONTROLLED_TRACK_ENTITIES
    assert standard == {
        ConfigEntityType.SEARCH_CONFIGURATION,
        ConfigEntityType.NOTIFICATION_TEMPLATE,
    }


def test_super_admin_approval_is_narrower_than_controlled_track() -> None:
    assert {
        ConfigEntityType.ROLE_DEFINITION,
        ConfigEntityType.PLATFORM_SETTINGS,
    } == SUPER_ADMIN_APPROVAL_ENTITIES
    assert SUPER_ADMIN_APPROVAL_ENTITIES <= CONTROLLED_TRACK_ENTITIES


def test_authoring_track_function_matches_the_frozenset() -> None:
    for entity_type in ConfigEntityType:
        expected = (
            AuthoringTrack.CONTROLLED
            if entity_type in CONTROLLED_TRACK_ENTITIES
            else AuthoringTrack.STANDARD
        )
        assert authoring_track(entity_type) is expected


def test_requires_super_admin_approval_function_matches_the_frozenset() -> None:
    for entity_type in ConfigEntityType:
        assert requires_super_admin_approval(entity_type) == (
            entity_type in SUPER_ADMIN_APPROVAL_ENTITIES
        )


def test_table_name_map_covers_every_entity_type_snake_case() -> None:
    assert set(TABLE_NAME_BY_ENTITY_TYPE) == set(ConfigEntityType)
    for entity_type, table_name in TABLE_NAME_BY_ENTITY_TYPE.items():
        assert "-" not in table_name
        assert table_name == entity_type.value.replace("-", "_")
