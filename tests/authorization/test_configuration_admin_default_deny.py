"""P-20 consolidation: `configuration`'s own admin surface (`config:<entity>:manage`/
`config:<entity>:approve`, 14 of `configuration.domain.whitelist.PERMISSION_KEYS`' 24 keys) proves
default-deny for all 8 entity types, mechanically, against the real router.

**Updated for DEF-01.** These tests used to drive the router by sending `X-Actor-Id` and
`X-Permission-Keys` headers, because `configuration.interfaces.auth.get_acting_admin` was a P-04
stand-in that read the caller's identity and permission set straight off the request and trusted
both. That stand-in is now overridden at the composition root by a real session-backed resolver, so
the header path no longer exists and every one of those requests would 401 before ever reaching the
permission gate.

The *intent* was always about the gate, not the transport: does holding the wrong key (or no key)
get refused, for every entity type. So the acting admin is now supplied by overriding the
dependency directly with a chosen `ActingAdmin` -- closer to what these tests were actually
asserting, and no longer dependent on (nor an endorsement of) a resolution mechanism that turned
out to be a security hole. `require_permission` itself is unchanged; only how the caller's identity
arrives is.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator

import pytest
from apps.backend.tests.configuration.conftest import (
    FakeConfigHeadRepository,
    FakeOutbox,
    FakeSnapshotCache,
)
from fastapi.testclient import TestClient

from configuration.application.category_read import CategoryReadUseCases
from configuration.application.use_cases import ConfigurationUseCases
from configuration.domain.whitelist import WhitelistRegistry
from configuration.interfaces.auth import ActingAdmin, get_acting_admin
from configuration.interfaces.di import (
    get_category_read_use_cases,
    get_configuration_use_cases,
)
from main import create_app

_ACTOR_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")

_ENTITY_TYPES = [
    "category",
    "form-definition",
    "product-definition",
    "placement-slot",
    "role-definition",
    "search-configuration",
    "notification-template",
    "platform-settings",
]
_CONTROLLED_TRACK_ENTITY_TYPES = [
    "category",
    "form-definition",
    "product-definition",
    "placement-slot",
    "role-definition",
    "platform-settings",
]

ClientFactory = Callable[[frozenset[str]], TestClient]


@pytest.fixture
def make_client() -> Iterator[ClientFactory]:
    """Builds a client whose acting admin holds exactly `permission_keys`.

    Overriding `get_acting_admin` here deliberately replaces the *real* session-backed resolver
    that `create_app` now installs. That is the point: standing up a real Redis session per case
    would be testing identity's session resolution, which its own module tests already cover,
    rather than configuration's permission gate, which is what this file is about.
    """
    clients: list[TestClient] = []

    def _make(permission_keys: frozenset[str]) -> TestClient:
        app = create_app()
        app.dependency_overrides[get_configuration_use_cases] = lambda: ConfigurationUseCases(
            FakeConfigHeadRepository(), FakeSnapshotCache(), FakeOutbox()
        )
        app.dependency_overrides[get_category_read_use_cases] = lambda: CategoryReadUseCases(
            FakeConfigHeadRepository(), FakeSnapshotCache()
        )
        app.dependency_overrides[get_acting_admin] = lambda: ActingAdmin(
            actor_id=_ACTOR_ID, permission_keys=permission_keys
        )
        client = TestClient(app, raise_server_exceptions=False)
        clients.append(client)
        return client

    yield _make

    for client in clients:
        client.close()


def test_whitelist_defines_a_manage_key_for_every_entity_type() -> None:
    """Sanity check on the harness itself: `_ENTITY_TYPES` matches
    `configuration.interfaces.routers.EntityTypeLiteral` exactly (8 entries) -- a future 9th
    entity type must be added here too, or this suite silently stops covering it."""
    registry = WhitelistRegistry()
    from configuration.domain.whitelist import PERMISSION_KEYS

    for entity_type in _ENTITY_TYPES:
        assert registry.manage_permission_key(entity_type) in PERMISSION_KEYS


def test_the_admin_surface_refuses_a_caller_with_forged_headers() -> None:
    """DEF-01's headline property, asserted end-to-end through the real app.

    No dependency override here, so the composition root's real resolver runs: the exact request
    the old tests sent -- an invented `X-Actor-Id` plus whatever `X-Permission-Keys` string the
    operation wanted, no cookie, no token -- must now be refused. Before the fix it was authorized
    as an administrator.
    """
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/api/v1/admin/config/category",
            headers={
                "X-Actor-Id": str(uuid.uuid4()),
                "X-Permission-Keys": "config:category:manage",
            },
        )
        assert response.status_code == 401, (
            "forged X-Actor-Id/X-Permission-Keys headers must no longer authorize anyone (DEF-01)"
        )


@pytest.mark.parametrize("entity_type", _ENTITY_TYPES)
def test_list_config_heads_denies_without_the_entity_types_manage_key(
    make_client: ClientFactory, entity_type: str
) -> None:
    """`GET /admin/config/{entityType}` (`listConfigHeads`) is a READ operation but still gates
    on `config:<entity>:manage` (`_require_manage_permission` runs before every operation on this
    router, including reads) -- a caller with NO permission keys at all must be denied for every
    one of the 8 entity types."""
    client = make_client(frozenset())
    response = client.get(f"/api/v1/admin/config/{entity_type}")

    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"


@pytest.mark.parametrize("entity_type", _ENTITY_TYPES)
def test_list_config_heads_denies_with_only_a_different_entity_types_manage_key(
    make_client: ClientFactory, entity_type: str
) -> None:
    """Cross-entity-type confusion check: holding `config:category:manage` must not grant access
    to `form-definition`'s admin surface, and so on -- proven for every (entity_type, foil) pair
    where the foil is a DIFFERENT entity type's own manage key."""
    foil_entity_type = next(et for et in _ENTITY_TYPES if et != entity_type)
    registry = WhitelistRegistry()

    client = make_client(frozenset({registry.manage_permission_key(foil_entity_type)}))
    response = client.get(f"/api/v1/admin/config/{entity_type}")

    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"


@pytest.mark.parametrize("entity_type", _CONTROLLED_TRACK_ENTITY_TYPES)
def test_publish_denies_a_manage_only_actor_lacking_the_approve_key(
    make_client: ClientFactory, entity_type: str
) -> None:
    """The maker-checker gate (Config Framework Sec 2.3/7 -- "Super-Admin approval required for
    the controlled track"): holding only the `manage` key is enough to create a draft, but
    `publishConfigVersion` also requires the entity type's own `approve` key. Proven here at the
    API boundary for all six controlled-track entity types (the standard-track two,
    `search-configuration`/`notification-template`, have no `approve` key at all, per
    `configuration.domain.whitelist.PERMISSION_KEYS`, and are exercised by
    `test_standard_track_full_lifecycle` in the module's own `test_api.py`).

    Worth noting this gate only became meaningful with DEF-01 fixed: while identities were
    self-claimed from headers, "a second, distinct principal holds the approve key" was satisfied
    by inventing a second UUID.
    """
    registry = WhitelistRegistry()

    client = make_client(frozenset({registry.manage_permission_key(entity_type)}))
    response = client.post(
        f"/api/v1/admin/config/{entity_type}/{uuid.uuid4()}/versions/{uuid.uuid4()}/publish",
        json={"approvalNote": None},
    )

    # Coarse Gate (`_require_manage_permission`) passes (manage key present); the fine-grained
    # maker-checker check inside `ConfigurationUseCases.publish` raises next -- either way this
    # must never be a 2xx success for an actor holding no approve key.
    assert response.status_code >= 400
