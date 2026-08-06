"""Regression tests for DEF-01: the configuration admin API must not authorize a caller from
client-supplied headers.

`configuration/interfaces/auth.py::get_acting_admin` is a P-04 stand-in that reads `X-Actor-Id` and
`X-Permission-Keys` off the request and trusts both. It was never replaced, so every one of the 14
`admin/config/*` operations was authorizable by anyone who invented a UUID and a permission string
-- no cookie, no token, no account. Maker-checker looked intact and was vacuous (two self-claimed
UUIDs satisfy "two distinct principals"), and the audit trail recorded the forged ids as real
actors.

The fix is `composition_root.provide_configuration_acting_admin`, registered over that stand-in in
`main.create_app`. These tests pin the three properties that matter, and would all have failed
before it existed:

  1. the override is actually wired up (the stand-in's own existence is not the bug -- *nothing
     overriding it* was, and that is invisible until something asserts on the wiring)
  2. no session token means no authorization, rather than falling back to headers
  3. permission keys come from the server-resolved acting context, never from the request

Session resolution itself is monkeypatched rather than stood up against real Postgres/Redis: what
is under test is where the identity and permissions *come from*, not identity's own gate logic,
which its module tests already cover.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

import composition_root
import main
from configuration.interfaces.auth import ActingAdmin, get_acting_admin
from identity.application.exceptions import InvalidSessionTokenError


class _FakeTokenGenerator:
    """Stands in for the real HMAC hasher, which needs `SESSION_SIGNING_KEY` from the environment.
    These tests are about where identity and permissions come from, not about how the token is
    hashed, so requiring real infra config here would only make them fragile."""

    @staticmethod
    def hash_token(token: str) -> str:
        return f"hashed:{token}"


def test_the_header_trusting_stand_in_is_overridden_in_the_real_app() -> None:
    """The bug was an absent override, so this asserts on the wiring itself.

    A stand-in that is never replaced looks perfectly correct in isolation -- `get_acting_admin`
    does exactly what its docstring says. Only the composition root knows it was meant to be
    swapped, so only here can the omission be caught.
    """
    app = main.create_app()

    assert get_acting_admin in app.dependency_overrides, (
        "configuration's header-trusting get_acting_admin stand-in is not overridden -- every "
        "admin/config/* operation is authorizable from client-supplied headers (DEF-01)"
    )
    assert (
        app.dependency_overrides[get_acting_admin]
        is composition_root.provide_configuration_acting_admin
    )


async def test_no_session_token_is_refused_outright() -> None:
    """No cookie and no Bearer means no authorization -- there is no header fallback left."""
    with pytest.raises(InvalidSessionTokenError):
        await composition_root.provide_configuration_acting_admin(
            ah_session=None, authorization=None
        )


async def test_permissions_come_from_the_resolved_context_not_the_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The core of DEF-01: identity and permission keys are whatever the *server* resolved for
    that session, and the request cannot contribute either one."""
    real_account_id = uuid4()
    server_side_permissions = frozenset({"config:category:manage"})

    class _FakeAccount:
        class _Id:
            value = real_account_id

        id = _Id()

    class _FakeContext:
        account_id = real_account_id
        acting_profile_id = None
        effective_permissions = server_side_permissions

    class _FakeAuthz:
        def __init__(self, **_kwargs: object) -> None: ...

        async def resolve_acting_context(
            self, *, token_hash: str, now: object
        ) -> tuple[object, object, object]:
            assert token_hash, "the raw token must be hashed before resolution"
            return _FakeAccount(), object(), _FakeContext()

    async def _fake_identity_session():  # type: ignore[no-untyped-def]
        yield object()

    monkeypatch.setattr(composition_root, "ApplicationAuthorizationService", _FakeAuthz)
    monkeypatch.setattr(composition_root, "_identity_session", _fake_identity_session)
    monkeypatch.setattr(
        composition_root, "SqlalchemyUserAccountRepository", lambda _session: object()
    )
    monkeypatch.setattr(composition_root, "RedisSessionRepository", lambda _client: object())
    monkeypatch.setattr(composition_root, "_identity_redis_client", lambda: object())
    monkeypatch.setattr(composition_root, "_role_definition_reader", lambda: object())
    monkeypatch.setattr(composition_root, "_session_token_generator", _FakeTokenGenerator)

    admin = await composition_root.provide_configuration_acting_admin(
        ah_session="a-real-looking-session-token", authorization=None
    )

    assert isinstance(admin, ActingAdmin)
    assert admin.actor_id == real_account_id
    assert admin.permission_keys == server_side_permissions


async def test_a_forged_permission_string_cannot_reach_the_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DEF-01's exact reproduction, inverted.

    The old stand-in would have returned `config:role-definition:approve` here purely because the
    caller asked for it. The resolver's signature accepts no such input at all -- the only way in
    is the session -- so a caller holding a valid session for an unprivileged account gets that
    account's real (empty) permission set regardless of what else they send.
    """
    unprivileged_id = uuid4()

    class _FakeAccount:
        class _Id:
            value = unprivileged_id

        id = _Id()

    class _FakeContext:
        account_id = unprivileged_id
        acting_profile_id = None
        effective_permissions: frozenset[str] = frozenset()

    class _FakeAuthz:
        def __init__(self, **_kwargs: object) -> None: ...

        async def resolve_acting_context(self, **_kwargs: object) -> tuple[object, object, object]:
            return _FakeAccount(), object(), _FakeContext()

    async def _fake_identity_session():  # type: ignore[no-untyped-def]
        yield object()

    monkeypatch.setattr(composition_root, "ApplicationAuthorizationService", _FakeAuthz)
    monkeypatch.setattr(composition_root, "_identity_session", _fake_identity_session)
    monkeypatch.setattr(
        composition_root, "SqlalchemyUserAccountRepository", lambda _session: object()
    )
    monkeypatch.setattr(composition_root, "RedisSessionRepository", lambda _client: object())
    monkeypatch.setattr(composition_root, "_identity_redis_client", lambda: object())
    monkeypatch.setattr(composition_root, "_role_definition_reader", lambda: object())
    monkeypatch.setattr(composition_root, "_session_token_generator", _FakeTokenGenerator)

    admin = await composition_root.provide_configuration_acting_admin(
        ah_session="valid-session-for-an-unprivileged-account", authorization=None
    )

    assert admin.permission_keys == frozenset()
    assert admin.actor_id == unprivileged_id
    # And the router-level gate then denies, which is the whole point of resolving honestly.
    from configuration.interfaces.auth import PermissionDeniedError, require_permission

    with pytest.raises(PermissionDeniedError):
        require_permission(admin, "config:category:manage")


def test_acting_admin_actor_id_is_a_uuid_not_a_value_object() -> None:
    """`ActingAdmin.actor_id` is a plain `UUID` while identity's `account.id` is a `UserId` value
    object, so the resolver has to unwrap `.value`. Getting that wrong would only surface wherever
    the audit trail writes the actor, which is exactly the field DEF-01 poisoned."""
    admin = ActingAdmin(actor_id=uuid4(), permission_keys=frozenset())
    assert isinstance(admin.actor_id, UUID)
