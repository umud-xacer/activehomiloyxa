"""The reusable authorization allow/deny matrix test harness (tests/README.md: "The authorization
matrix suite (allow/deny per permission key + ownership) is release-blocking (TEST-02, QG-08) and
belongs here"; P-05 prompt: "This module's tests must also produce the FIRST version of the
reusable authorization allow/deny matrix test harness ... later modules will extend this same
harness rather than building their own").

Each `AuthorizationScenario` is one row: an acting context's granted permissions + acting
profile, a required permission for the operation under test, and the target resource's
ownership -- with the expected allow/deny outcome. `run_authorization_matrix` drives
`identity.domain.AuthorizationService.authorize` (Security Sec 4.2 Gates 3-4) against every
scenario, so this file is the single place the four-gate model's *decision logic* is exercised
end-to-end across every scenario any module contributes.

To extend: build your own `list[AuthorizationScenario]` (your module's permission keys and
ownership shapes) and call `run_authorization_matrix(IDENTITY_MATRIX + your_scenarios)`, or just
your own list alone, from your own test module (`from tests.authorization.matrix import ...`) --
no need to reimplement the harness or import anything from `identity.domain` directly.

Covers every permission key that is actually consulted through `identity.domain.
AuthorizationService.authorize` (P-20's own consolidation: `composition_root.py`'s own
`AuthorizationService().authorize(context, ...)` call sites are the exhaustive, mechanically-
verifiable list of which of `configuration.domain.whitelist.PERMISSION_KEYS`' 24 keys this harness
must cover). `config:*:manage`/`config:*:approve` (14 keys) are NOT covered here -- they are
checked by a DIFFERENT mechanism entirely (`configuration.interfaces.auth.require_permission`, a
flat header-based membership check, not `identity.domain.AuthorizationService`) -- see
`tests/authorization/test_configuration_admin_default_deny.py` for that surface instead.
`catalog:listing:moderate`/`profiles:profile:moderate` are declared in the whitelist but, by
design (I-24), never re-checked as their own `AuthorizationService.authorize` call anywhere at
runtime -- the single gate for the whole moderation-action flow is `moderation:case:review` at
the router boundary; see `PROFILES_MATRIX`'s own comment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

import pytest

from identity.domain import (
    ActingContext,
    AuthorizationService,
    PermissionDeniedError,
    WrongActingProfileError,
)
from shared_kernel import BusinessProfileId, UserId


@dataclass(frozen=True)
class AuthorizationScenario:
    """One row of the allow/deny matrix."""

    name: str
    granted_permissions: frozenset[str]
    required_permission: str
    acting_profile_id: BusinessProfileId | None = None
    owner_account_id: UserId | None = None
    owner_profile_id: BusinessProfileId | None = None
    account_id: UserId = field(default_factory=lambda: UserId(value=uuid4()))
    expect_allowed: bool = False
    expect_exception: type[Exception] | None = None


def run_authorization_matrix(scenarios: list[AuthorizationScenario]) -> None:
    """Runs every scenario against a fresh `AuthorizationService` (stateless -- one instance
    would work equally well, but a fresh one per call keeps scenarios fully independent of any
    hidden internal state, of which there currently is none)."""
    service = AuthorizationService()
    for scenario in scenarios:
        context = ActingContext(
            account_id=scenario.account_id,
            acting_profile_id=scenario.acting_profile_id,
            effective_permissions=scenario.granted_permissions,
        )
        if scenario.expect_allowed:
            service.authorize(
                context,
                scenario.required_permission,
                owner_account_id=scenario.owner_account_id,
                owner_profile_id=scenario.owner_profile_id,
            )
            continue

        expected_exception = scenario.expect_exception or PermissionDeniedError
        with pytest.raises(expected_exception):
            service.authorize(
                context,
                scenario.required_permission,
                owner_account_id=scenario.owner_account_id,
                owner_profile_id=scenario.owner_profile_id,
            )


_SHARED_ACCOUNT = UserId(value=uuid4())
_PROFILE_A = BusinessProfileId(value=uuid4())
_PROFILE_B = BusinessProfileId(value=uuid4())

IDENTITY_MATRIX: list[AuthorizationScenario] = [
    AuthorizationScenario(
        name="no_permissions_denied",
        granted_permissions=frozenset(),
        required_permission="identity:role:assign",
        expect_allowed=False,
        expect_exception=PermissionDeniedError,
    ),
    AuthorizationScenario(
        name="unrelated_permission_denied",
        granted_permissions=frozenset({"identity:account:manage_status"}),
        required_permission="identity:role:assign",
        expect_allowed=False,
        expect_exception=PermissionDeniedError,
    ),
    AuthorizationScenario(
        name="exact_permission_granted_allowed",
        granted_permissions=frozenset({"identity:role:assign"}),
        required_permission="identity:role:assign",
        expect_allowed=True,
    ),
    AuthorizationScenario(
        name="profile_scoped_permission_matches_acting_profile_allowed",
        granted_permissions=frozenset({"catalog:listing:manage"}),
        required_permission="catalog:listing:manage",
        acting_profile_id=_PROFILE_A,
        owner_profile_id=_PROFILE_A,
        expect_allowed=True,
    ),
    AuthorizationScenario(
        name="profile_scoped_permission_wrong_profile_denied",
        granted_permissions=frozenset({"catalog:listing:manage"}),
        required_permission="catalog:listing:manage",
        acting_profile_id=_PROFILE_A,
        owner_profile_id=_PROFILE_B,
        expect_allowed=False,
        expect_exception=WrongActingProfileError,
    ),
    AuthorizationScenario(
        name="personal_context_cannot_act_on_a_profile_resource",
        granted_permissions=frozenset({"catalog:listing:manage"}),
        required_permission="catalog:listing:manage",
        acting_profile_id=None,
        owner_profile_id=_PROFILE_A,
        expect_allowed=False,
        expect_exception=WrongActingProfileError,
    ),
    AuthorizationScenario(
        name="self_service_own_account_allowed",
        granted_permissions=frozenset({"identity:account:self"}),
        required_permission="identity:account:self",
        account_id=_SHARED_ACCOUNT,
        owner_account_id=_SHARED_ACCOUNT,
        expect_allowed=True,
    ),
    AuthorizationScenario(
        name="self_service_another_account_denied",
        granted_permissions=frozenset({"identity:account:self"}),
        required_permission="identity:account:self",
        account_id=_SHARED_ACCOUNT,
        owner_account_id=UserId(value=uuid4()),
        expect_allowed=False,
        expect_exception=WrongActingProfileError,
    ),
    # P-20: `identity:account:manage_status` (`adminChangeUserStatus`, ADR-0006's own
    # `composition_root.provide_users_acting_operator`) previously only appeared as an
    # "unrelated permission" foil above -- never proven as its own allow/deny pair. Same
    # operator-wide shape as `billing:invoice:confirm_payment`/`moderation:case:review` (Gate 3
    # only, no ownership scoping: the operator changing a user's status never has to "own" that
    # account).
    AuthorizationScenario(
        name="account_manage_status_no_permissions_denied",
        granted_permissions=frozenset(),
        required_permission="identity:account:manage_status",
        expect_allowed=False,
        expect_exception=PermissionDeniedError,
    ),
    AuthorizationScenario(
        name="account_manage_status_unrelated_permission_denied",
        granted_permissions=frozenset({"identity:role:assign"}),
        required_permission="identity:account:manage_status",
        expect_allowed=False,
        expect_exception=PermissionDeniedError,
    ),
    AuthorizationScenario(
        name="account_manage_status_exact_permission_granted_allowed",
        granted_permissions=frozenset({"identity:account:manage_status"}),
        required_permission="identity:account:manage_status",
        expect_allowed=True,
    ),
]

# Task P-07 (catalog/BC-03) extends the harness with scenarios for its own permission key,
# `catalog:listing:moderate` (`catalog.application.listing_use_cases.ListingUseCases.
# unflag_listing`, the moderation-invoked command port -- `catalog.interfaces.moderation_port`).
# Catalog's own self-service CRUD operations never call `AuthorizationService.authorize` (they
# are ownership-gated via `catalog.domain.exceptions.NotListingOwnerError`, mirroring media's own
# self-service model); this is the one place catalog's permission key crosses the same
# default-deny/profile-scoping decision logic identity's own matrix already proves generically.
_CATALOG_PROFILE_A = BusinessProfileId(value=uuid4())
_CATALOG_PROFILE_B = BusinessProfileId(value=uuid4())

CATALOG_MATRIX: list[AuthorizationScenario] = [
    AuthorizationScenario(
        name="catalog_moderate_no_permissions_denied",
        granted_permissions=frozenset(),
        required_permission="catalog:listing:moderate",
        expect_allowed=False,
        expect_exception=PermissionDeniedError,
    ),
    AuthorizationScenario(
        name="catalog_moderate_unrelated_permission_denied",
        granted_permissions=frozenset({"catalog:listing:manage"}),
        required_permission="catalog:listing:moderate",
        expect_allowed=False,
        expect_exception=PermissionDeniedError,
    ),
    AuthorizationScenario(
        name="catalog_moderate_exact_permission_granted_allowed",
        granted_permissions=frozenset({"catalog:listing:moderate"}),
        required_permission="catalog:listing:moderate",
        expect_allowed=True,
    ),
    AuthorizationScenario(
        name="catalog_moderate_profile_scoped_matches_acting_profile_allowed",
        granted_permissions=frozenset({"catalog:listing:moderate"}),
        required_permission="catalog:listing:moderate",
        acting_profile_id=_CATALOG_PROFILE_A,
        owner_profile_id=_CATALOG_PROFILE_A,
        expect_allowed=True,
    ),
    AuthorizationScenario(
        name="catalog_moderate_wrong_acting_profile_denied",
        granted_permissions=frozenset({"catalog:listing:moderate"}),
        required_permission="catalog:listing:moderate",
        acting_profile_id=_CATALOG_PROFILE_A,
        owner_profile_id=_CATALOG_PROFILE_B,
        expect_allowed=False,
        expect_exception=WrongActingProfileError,
    ),
]

# Task P-09 (billing/BC-08) extends the harness with scenarios for its own permission key,
# `billing:invoice:confirm_payment` (`billing.application.payment_use_cases.PaymentUseCases.
# confirm_payment`, invoked only via the admin-facing `confirmInvoicePayment` operation --
# `composition_root.provide_billing_acting_operator` is the one caller anywhere in this codebase
# that runs `AuthorizationService.authorize` against it). Unlike catalog's `catalog:listing:
# moderate` (profile-scoped, Gate 4), this is a pure operator-wide capability -- the confirming
# operator never has to "own" the invoice/order/profile they're confirming payment for, so no
# `owner_account_id`/`owner_profile_id` is ever passed at the real call site and only Gate 3 (the
# permission-membership check) applies here.
BILLING_MATRIX: list[AuthorizationScenario] = [
    AuthorizationScenario(
        name="billing_confirm_payment_no_permissions_denied",
        granted_permissions=frozenset(),
        required_permission="billing:invoice:confirm_payment",
        expect_allowed=False,
        expect_exception=PermissionDeniedError,
    ),
    AuthorizationScenario(
        name="billing_confirm_payment_unrelated_permission_denied",
        granted_permissions=frozenset({"catalog:listing:manage"}),
        required_permission="billing:invoice:confirm_payment",
        expect_allowed=False,
        expect_exception=PermissionDeniedError,
    ),
    AuthorizationScenario(
        name="billing_confirm_payment_exact_permission_granted_allowed",
        granted_permissions=frozenset({"billing:invoice:confirm_payment"}),
        required_permission="billing:invoice:confirm_payment",
        expect_allowed=True,
    ),
]

# Task P-11 (profiles/BC-02) extends the harness with scenarios for its own two permission keys.
# `profiles:verification:review` gates `listVerificationQueue`/`decideVerification`
# (`composition_root.provide_profiles_acting_reviewer` is the one caller that runs
# `AuthorizationService.authorize` against it) -- an operator-wide capability like billing's own
# `billing:invoice:confirm_payment` (Gate 3 only, no ownership scoping: a reviewer never has to
# "own" the business profile whose case they are deciding). `profiles:profile:moderate` gates the
# moderation-invoked command port (`profiles.interfaces.moderation_port.ProfileModerationPort`) --
# profile-scoped like catalog's own `catalog:listing:moderate` (Gate 4 applies), declared but not
# yet consulted anywhere, pending a future moderation module, the same "capability exists, no
# caller wires it yet" status catalog's own equivalent key documents.
_PROFILES_PROFILE_A = BusinessProfileId(value=uuid4())
_PROFILES_PROFILE_B = BusinessProfileId(value=uuid4())

PROFILES_MATRIX: list[AuthorizationScenario] = [
    AuthorizationScenario(
        name="profiles_review_no_permissions_denied",
        granted_permissions=frozenset(),
        required_permission="profiles:verification:review",
        expect_allowed=False,
        expect_exception=PermissionDeniedError,
    ),
    AuthorizationScenario(
        name="profiles_review_unrelated_permission_denied",
        granted_permissions=frozenset({"catalog:listing:manage"}),
        required_permission="profiles:verification:review",
        expect_allowed=False,
        expect_exception=PermissionDeniedError,
    ),
    AuthorizationScenario(
        name="profiles_review_exact_permission_granted_allowed",
        granted_permissions=frozenset({"profiles:verification:review"}),
        required_permission="profiles:verification:review",
        expect_allowed=True,
    ),
    AuthorizationScenario(
        name="profiles_moderate_no_permissions_denied",
        granted_permissions=frozenset(),
        required_permission="profiles:profile:moderate",
        expect_allowed=False,
        expect_exception=PermissionDeniedError,
    ),
    AuthorizationScenario(
        name="profiles_moderate_exact_permission_granted_allowed",
        granted_permissions=frozenset({"profiles:profile:moderate"}),
        required_permission="profiles:profile:moderate",
        expect_allowed=True,
    ),
    AuthorizationScenario(
        name="profiles_moderate_profile_scoped_matches_acting_profile_allowed",
        granted_permissions=frozenset({"profiles:profile:moderate"}),
        required_permission="profiles:profile:moderate",
        acting_profile_id=_PROFILES_PROFILE_A,
        owner_profile_id=_PROFILES_PROFILE_A,
        expect_allowed=True,
    ),
    AuthorizationScenario(
        name="profiles_moderate_wrong_acting_profile_denied",
        granted_permissions=frozenset({"profiles:profile:moderate"}),
        required_permission="profiles:profile:moderate",
        acting_profile_id=_PROFILES_PROFILE_A,
        owner_profile_id=_PROFILES_PROFILE_B,
        expect_allowed=False,
        expect_exception=WrongActingProfileError,
    ),
]

# Task P-12 (moderation/BC-11) extends the harness with scenarios for its one permission key,
# `moderation:case:review` (`listModerationQueue`/`getModerationCase`/`applyModerationAction` --
# `composition_root.provide_moderation_acting_moderator` is the one caller that runs
# `AuthorizationService.authorize` against it). An operator-wide capability like billing's own
# `billing:invoice:confirm_payment` and profiles' own `profiles:verification:review` (Gate 3
# only, no ownership scoping): a moderator never has to "own" the listing/user/profile/
# conversation whose case they are reviewing -- moderation is a trust-and-safety capability, not
# a self-service one.
MODERATION_MATRIX: list[AuthorizationScenario] = [
    AuthorizationScenario(
        name="moderation_review_no_permissions_denied",
        granted_permissions=frozenset(),
        required_permission="moderation:case:review",
        expect_allowed=False,
        expect_exception=PermissionDeniedError,
    ),
    AuthorizationScenario(
        name="moderation_review_unrelated_permission_denied",
        granted_permissions=frozenset({"catalog:listing:manage"}),
        required_permission="moderation:case:review",
        expect_allowed=False,
        expect_exception=PermissionDeniedError,
    ),
    AuthorizationScenario(
        name="moderation_review_exact_permission_granted_allowed",
        granted_permissions=frozenset({"moderation:case:review"}),
        required_permission="moderation:case:review",
        expect_allowed=True,
    ),
]

# P-20 consolidation: Task P-14 (ads/BC-09) extends the catalogue with `ads:campaign:manage`,
# gating all seven `/admin/campaigns*` operator operations (ADR-0004) --
# `composition_root.provide_ads_acting_operator` calls the real `AuthorizationService.authorize`
# against it. Operator-wide capability (Gate 3 only), like billing's/moderation's own.
ADS_MATRIX: list[AuthorizationScenario] = [
    AuthorizationScenario(
        name="ads_campaign_manage_no_permissions_denied",
        granted_permissions=frozenset(),
        required_permission="ads:campaign:manage",
        expect_allowed=False,
        expect_exception=PermissionDeniedError,
    ),
    AuthorizationScenario(
        name="ads_campaign_manage_unrelated_permission_denied",
        granted_permissions=frozenset({"billing:invoice:confirm_payment"}),
        required_permission="ads:campaign:manage",
        expect_allowed=False,
        expect_exception=PermissionDeniedError,
    ),
    AuthorizationScenario(
        name="ads_campaign_manage_exact_permission_granted_allowed",
        granted_permissions=frozenset({"ads:campaign:manage"}),
        required_permission="ads:campaign:manage",
        expect_allowed=True,
    ),
]

# P-20 consolidation: Task P-15 (analytics/BC-13) extends the catalogue with
# `analytics:audit:read` (`queryAuditLog`) and `analytics:reports:read` (`getAdminReports`) --
# `composition_root.provide_audit_acting_operator`/`provide_reports_acting_operator` call the
# real `AuthorizationService.authorize` against each. Two DISTINCT keys -- holding one must not
# grant the other (proven below, not merely assumed from the two being "similar").
ANALYTICS_MATRIX: list[AuthorizationScenario] = [
    AuthorizationScenario(
        name="analytics_audit_read_no_permissions_denied",
        granted_permissions=frozenset(),
        required_permission="analytics:audit:read",
        expect_allowed=False,
        expect_exception=PermissionDeniedError,
    ),
    AuthorizationScenario(
        name="analytics_audit_read_reports_permission_does_not_grant_audit_denied",
        granted_permissions=frozenset({"analytics:reports:read"}),
        required_permission="analytics:audit:read",
        expect_allowed=False,
        expect_exception=PermissionDeniedError,
    ),
    AuthorizationScenario(
        name="analytics_audit_read_exact_permission_granted_allowed",
        granted_permissions=frozenset({"analytics:audit:read"}),
        required_permission="analytics:audit:read",
        expect_allowed=True,
    ),
    AuthorizationScenario(
        name="analytics_reports_read_no_permissions_denied",
        granted_permissions=frozenset(),
        required_permission="analytics:reports:read",
        expect_allowed=False,
        expect_exception=PermissionDeniedError,
    ),
    AuthorizationScenario(
        name="analytics_reports_read_audit_permission_does_not_grant_reports_denied",
        granted_permissions=frozenset({"analytics:audit:read"}),
        required_permission="analytics:reports:read",
        expect_allowed=False,
        expect_exception=PermissionDeniedError,
    ),
    AuthorizationScenario(
        name="analytics_reports_read_exact_permission_granted_allowed",
        granted_permissions=frozenset({"analytics:reports:read"}),
        required_permission="analytics:reports:read",
        expect_allowed=True,
    ),
]

# P-20 consolidation: Task P-16 (admin/BC-12) adds `admin:dashboard:read`, gating
# `getAdminDashboard` -- the ONE operation genuinely admin's own (`composition_root.
# provide_admin_acting_operator` calls the real `AuthorizationService.authorize` against it).
ADMIN_MATRIX: list[AuthorizationScenario] = [
    AuthorizationScenario(
        name="admin_dashboard_read_no_permissions_denied",
        granted_permissions=frozenset(),
        required_permission="admin:dashboard:read",
        expect_allowed=False,
        expect_exception=PermissionDeniedError,
    ),
    AuthorizationScenario(
        name="admin_dashboard_read_unrelated_permission_denied",
        granted_permissions=frozenset({"moderation:case:review"}),
        required_permission="admin:dashboard:read",
        expect_allowed=False,
        expect_exception=PermissionDeniedError,
    ),
    AuthorizationScenario(
        name="admin_dashboard_read_exact_permission_granted_allowed",
        granted_permissions=frozenset({"admin:dashboard:read"}),
        required_permission="admin:dashboard:read",
        expect_allowed=True,
    ),
]
