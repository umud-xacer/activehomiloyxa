"""Role permission flattening (Config Framework Sec 7.1-7.2; I-11: "permission semantics are
immutable at runtime" -- no runtime inheritance, flattened once at publish)."""

from __future__ import annotations

from configuration.domain.permissions import flatten_role_permissions


def test_direct_keys_only() -> None:
    result = flatten_role_permissions(
        direct_keys=["config:category:manage"],
        group_codes=[],
        permission_keys_by_group_code={},
        parent_role_flattened_keys=frozenset(),
    )
    assert result == ["config:category:manage"]


def test_group_codes_are_expanded_and_merged() -> None:
    result = flatten_role_permissions(
        direct_keys=["a"],
        group_codes=["moderators"],
        permission_keys_by_group_code={"moderators": frozenset({"b", "c"})},
        parent_role_flattened_keys=frozenset(),
    )
    assert result == ["a", "b", "c"]


def test_parent_role_keys_are_merged_in() -> None:
    result = flatten_role_permissions(
        direct_keys=["a"],
        group_codes=[],
        permission_keys_by_group_code={},
        parent_role_flattened_keys=frozenset({"b"}),
    )
    assert result == ["a", "b"]


def test_duplicates_across_sources_are_deduplicated_and_sorted() -> None:
    result = flatten_role_permissions(
        direct_keys=["b", "a"],
        group_codes=["g"],
        permission_keys_by_group_code={"g": frozenset({"a", "c"})},
        parent_role_flattened_keys=frozenset({"c", "d"}),
    )
    assert result == ["a", "b", "c", "d"]


def test_unknown_group_code_contributes_nothing() -> None:
    result = flatten_role_permissions(
        direct_keys=["a"],
        group_codes=["nonexistent"],
        permission_keys_by_group_code={},
        parent_role_flattened_keys=frozenset(),
    )
    assert result == ["a"]
