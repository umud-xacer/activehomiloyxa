"""Role permission flattening (Config Framework Sec 7.1-7.2; Physical DB Sec 2.4
`role_definition_version.permission_keys`). Permission groups and role hierarchy are
authoring-time composition aids only; both are flattened into one concrete `permission_keys`
list at publish -- there is no runtime inheritance (I-11: "permission semantics are immutable at
runtime"). Pure function over pre-fetched facts (Clean Architecture rule 1): the calling use
case resolves group contents and the parent role's own flattened keys via repository ports.
"""

from __future__ import annotations


def flatten_role_permissions(
    *,
    direct_keys: list[str],
    group_codes: list[str],
    permission_keys_by_group_code: dict[str, frozenset[str]],
    parent_role_flattened_keys: frozenset[str],
) -> list[str]:
    flattened: set[str] = set(direct_keys)
    for group_code in group_codes:
        flattened |= permission_keys_by_group_code.get(group_code, frozenset())
    flattened |= parent_role_flattened_keys
    return sorted(flattened)
