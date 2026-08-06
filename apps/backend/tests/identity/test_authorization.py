"""Unit tests for `identity.domain.AuthorizationService` -- the single highest-stakes piece of
this module (Security Sec 4: "the platform's highest-stakes security property"). Named per the
P-05 prompt's explicit validation checklist, which labels the default-deny test "(I-10 test)" and
the profile-scoping test "(I-11 test)"; DDD Sec 9's own I-10 text ("cross-profile access is
denied by default") already covers both halves of that pairing in one invariant statement, and
I-11 ("permission semantics are immutable at runtime... no implicit escalation path") is covered
here by the dedicated escalation-attempt test. Every test below calls
`AuthorizationService.authorize` directly -- the actual default-deny code path, not a mock of it.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from identity.domain import (
    ActingContext,
    AuthorizationService,
    PermissionDeniedError,
    WrongActingProfileError,
)
from shared_kernel import BusinessProfileId, UserId
from tests.authorization.matrix import IDENTITY_MATRIX, run_authorization_matrix


@pytest.fixture
def service() -> AuthorizationService:
    return AuthorizationService()


def _context(**overrides: object) -> ActingContext:
    defaults: dict[str, object] = {
        "account_id": UserId(value=uuid4()),
        "acting_profile_id": None,
        "effective_permissions": frozenset(),
    }
    defaults.update(overrides)
    return ActingContext(**defaults)  # type: ignore[arg-type]


# --- I-10: default-deny -------------------------------------------------------------------


def test_I10_default_deny_operation_with_zero_permissions_is_denied(
    service: AuthorizationService,
) -> None:
    """Validation checklist: "an operation with no granted permission is denied, not merely
    'not explicitly allowed'" -- the acting context here holds *zero* permissions of any kind,
    proving denial is the default outcome of the actual `authorize()` code path, not a side
    effect of some other check happening to also fail."""
    context = _context(effective_permissions=frozenset())
    with pytest.raises(PermissionDeniedError) as exc_info:
        service.authorize(context, "identity:role:assign")
    assert exc_info.value.required_permission == "identity:role:assign"


def test_I10_unrelated_permissions_do_not_satisfy_a_different_required_permission(
    service: AuthorizationService,
) -> None:
    """Holding *some* permissions is not enough -- only the exact required key satisfies Gate 3.
    Proves membership is exact-match, not "the set is non-empty"."""
    context = _context(
        effective_permissions=frozenset({"identity:account:manage_status", "identity:role"})
    )
    with pytest.raises(PermissionDeniedError):
        service.authorize(context, "identity:role:assign")


def test_I10_cross_profile_access_denied_by_default(service: AuthorizationService) -> None:
    """DDD Sec 9 I-10 verbatim: "cross-profile access is denied by default." A resource owned by
    profile B is denied even though the permission itself is held, while acting as profile A."""
    profile_a = BusinessProfileId(value=uuid4())
    profile_b = BusinessProfileId(value=uuid4())
    context = _context(
        acting_profile_id=profile_a, effective_permissions=frozenset({"catalog:listing:manage"})
    )
    with pytest.raises(WrongActingProfileError):
        service.authorize(context, "catalog:listing:manage", owner_profile_id=profile_b)


def test_I10_permission_held_grants_access_only_when_scope_matches(
    service: AuthorizationService,
) -> None:
    """The success path: holding the permission AND matching scope is the one way through."""
    profile_a = BusinessProfileId(value=uuid4())
    context = _context(
        acting_profile_id=profile_a, effective_permissions=frozenset({"catalog:listing:manage"})
    )
    service.authorize(context, "catalog:listing:manage", owner_profile_id=profile_a)  # no raise


# --- I-11: per-acting-profile scoping (no leakage) + fixed permission semantics --------------


def test_I11_permission_granted_under_profile_a_denied_when_acting_as_profile_b(
    service: AuthorizationService,
) -> None:
    """Validation checklist: "a permission held under one acting profile must not leak to
    another acting profile of the same account" -- same account, same permission key, only the
    acting profile changes between the two calls."""
    account_id = UserId(value=uuid4())
    profile_a = BusinessProfileId(value=uuid4())
    profile_b = BusinessProfileId(value=uuid4())
    permissions = frozenset({"catalog:listing:manage"})

    context_as_a = _context(
        account_id=account_id, acting_profile_id=profile_a, effective_permissions=permissions
    )
    service.authorize(context_as_a, "catalog:listing:manage", owner_profile_id=profile_a)

    context_as_b = _context(
        account_id=account_id, acting_profile_id=profile_b, effective_permissions=permissions
    )
    with pytest.raises(WrongActingProfileError):
        service.authorize(context_as_b, "catalog:listing:manage", owner_profile_id=profile_a)


def test_I11_permission_held_in_personal_context_does_not_leak_into_a_profile_context(
    service: AuthorizationService,
) -> None:
    account_id = UserId(value=uuid4())
    profile = BusinessProfileId(value=uuid4())
    context_personal = _context(
        account_id=account_id,
        acting_profile_id=None,
        effective_permissions=frozenset({"catalog:listing:manage"}),
    )
    with pytest.raises(WrongActingProfileError):
        service.authorize(context_personal, "catalog:listing:manage", owner_profile_id=profile)


def test_I11_escalation_attempt_via_unrelated_granted_key_is_blocked(
    service: AuthorizationService,
) -> None:
    """Validation checklist: "test attempts an escalation and confirms it is blocked" -- DDD
    Sec 9 I-11: "permission semantics are immutable at runtime ... no implicit escalation path."
    Holding every OTHER permission in the catalogue does not imply holding the one actually
    required -- there is no wildcard, hierarchy walk, or prefix match in `authorize()`."""
    context = _context(
        effective_permissions=frozenset(
            {
                "identity:account:manage_status",
                "config:role-definition:manage",
                "config:role-definition:approve",
            }
        )
    )
    with pytest.raises(PermissionDeniedError):
        service.authorize(context, "identity:role:assign")


def test_I11_owning_a_different_account_does_not_grant_self_service_access(
    service: AuthorizationService,
) -> None:
    """Gate 4 for account-scoped (not profile-scoped) resources: acting in the personal context
    only authorizes actions on the caller's own account."""
    context = _context(
        account_id=UserId(value=uuid4()), effective_permissions=frozenset({"identity:account:self"})
    )
    other_account = UserId(value=uuid4())
    with pytest.raises(WrongActingProfileError):
        service.authorize(context, "identity:account:self", owner_account_id=other_account)


# --- reusable authorization allow/deny matrix harness (first version, P-05) ------------------


def test_authorization_matrix_harness_identity_scenarios() -> None:
    """Runs identity's own baseline scenarios through the shared, extensible harness at
    `tests/authorization/matrix.py` (consolidated there in P-20; was `tests/authorization_matrix.
    py` from P-05 through P-19) -- later modules import `run_authorization_matrix` and
    contribute their own `AuthorizationScenario` list rather than building a second harness."""
    run_authorization_matrix(IDENTITY_MATRIX)
