"""Ports the generic use cases depend on (Playbook Sec 6: "application/ depends on ports;
infrastructure/ implements them"). One `ConfigHeadRepository` port, parametrized by
`ConfigEntityType` at call time -- the same "generic machinery instantiated eight times" pattern
as `domain/`, carried into the repository boundary (DB Architecture Sec 18: "exactly one
repository per aggregate root" -- here, one repository *port*, one adapter class, constructed
once per entity type at the composition root).
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from configuration.domain import ConfigEntityType, ConfigHead, ConfigVersion


class ConfigHeadRepository(Protocol):
    """Loads/saves whole Head+Version aggregates for one entity type. Child entities
    (FieldDefinition, FacetContent, ...) live inside `definition_document` and have no
    repositories of their own (DB Architecture Sec 18 "child entities have no repositories")."""

    async def get_head(self, entity_type: ConfigEntityType, head_id: UUID) -> ConfigHead | None: ...

    async def get_head_by_code(
        self, entity_type: ConfigEntityType, code: str
    ) -> ConfigHead | None: ...

    async def list_heads(
        self, entity_type: ConfigEntityType, *, cursor: str | None, limit: int
    ) -> tuple[list[ConfigHead], str | None]: ...

    async def list_versions(
        self, entity_type: ConfigEntityType, head_id: UUID
    ) -> list[ConfigVersion]: ...

    async def get_version(
        self, entity_type: ConfigEntityType, head_id: UUID, version_id: UUID
    ) -> ConfigVersion | None: ...

    async def latest_version_number(self, entity_type: ConfigEntityType, head_id: UUID) -> int: ...

    async def add_head(self, entity_type: ConfigEntityType, head: ConfigHead) -> None: ...

    async def add_version(self, entity_type: ConfigEntityType, version: ConfigVersion) -> None: ...

    async def update_version(
        self, entity_type: ConfigEntityType, version: ConfigVersion
    ) -> None: ...

    async def update_head(self, entity_type: ConfigEntityType, head: ConfigHead) -> None: ...

    async def existing_codes(
        self, entity_type: ConfigEntityType, *, exclude_head_id: UUID | None
    ) -> frozenset[str]: ...

    async def dependency_exists(self, kind: str, reference: str) -> bool: ...

    """`kind` is e.g. `"form-definition"`, `"category"`, `"permission-group"`,
    `"role-definition"`; `reference` is the referenced code/id as a string. True iff a head with
    that code exists in a publishable state (has a current, non-archived version)."""

    async def category_has_bound_listings(self, category_head_id: UUID) -> bool: ...

    """I-03. Stub in this task (catalog's Listing aggregate does not exist yet, Task P-04 scope
    excludes implementing other modules) -- the real adapter is catalog's own future task; the
    port and the domain check it feeds are fully implemented and tested now."""

    async def ancestor_codes(
        self, entity_type: ConfigEntityType, of_code: str
    ) -> frozenset[str]: ...

    """Category tree / role hierarchy cycle detection: codes of `of_code`'s full ancestor chain
    (its parent, its parent's parent, ...), inclusive of `of_code` itself if a cycle already
    exists."""

    async def permission_group_keys(self, codes: list[str]) -> dict[str, frozenset[str]]: ...

    async def role_flattened_permission_keys(self, role_code: str) -> frozenset[str]: ...

    async def conflicting_active_version_exists(
        self,
        entity_type: ConfigEntityType,
        head_id: UUID,
        *,
        validity_from: object,
        validity_until: object,
    ) -> bool: ...


class OwnerAdminLockoutPort(Protocol):
    """IP-scoped consecutive-wrong-guess counter behind `verifyOwnerAdminSlug`'s lockout
    (`interfaces/routers.py`). Same shape as `identity.application.ports.LoginAttemptTrackerPort`
    (single `identifier` here -- an IP -- since this endpoint has only one scope, unlike login's
    ip+account pair) -- kept as a `Protocol` here rather than importing `backbone.rate_limit`'s
    concrete `RedisWindowCounter` straight into `interfaces`: DEC-18 forbids a provider SDK/
    datastore client type (here, `redis`, transitively) crossing a module's `interfaces/`
    boundary. The real Redis-backed adapter lives in `infrastructure/`, wired at the composition
    root, exactly like `SnapshotCachePort`/`RedisSnapshotCache` below."""

    async def record_failure(self, *, identifier: str, window_seconds: int) -> int: ...

    async def get_failure_count(self, *, identifier: str) -> int: ...

    async def get_retry_after_seconds(self, *, identifier: str) -> int: ...

    async def reset(self, *, identifier: str) -> None: ...


class SnapshotCachePort(Protocol):
    """Redis-backed consumer-facing snapshot cache (Config Framework Sec 2.4: "Conforming
    consumers refresh their cached snapshots ... the platform keeps serving the last good
    snapshot if BC-04 is briefly unavailable")."""

    async def put(
        self, entity_type: ConfigEntityType, code: str, snapshot: dict[str, object]
    ) -> None: ...

    async def get(self, entity_type: ConfigEntityType, code: str) -> dict[str, object] | None: ...

    async def invalidate(self, entity_type: ConfigEntityType, code: str) -> None: ...

    async def list_current(self, entity_type: ConfigEntityType) -> list[dict[str, object]]: ...
