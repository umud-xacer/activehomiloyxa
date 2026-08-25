"""Unit tests for the `UserAccount` aggregate (DDD Sec 5.1): factories, every lifecycle
transition and its guard, profile scoping, and role assignment/revocation."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from identity.domain import (
    AccountKind,
    AccountNotActiveError,
    AccountStatus,
    AuthMethodType,
    EmailAddress,
    IllegalAccountStateTransitionError,
    PhoneNumber,
    PhoneRevealMode,
    PrivacySettings,
    RegistrationAlreadyDecidedError,
    RegistrationReviewStatus,
    RoleNotAssignedError,
    UnknownAuthenticationMethodError,
    UserAccount,
)
from shared_kernel import BusinessProfileId, UserId

NOW = datetime(2026, 7, 11, tzinfo=UTC)


def _new_account() -> UserAccount:
    return UserAccount.register_via_phone(
        account_id=UserId(value=uuid4()), phone=PhoneNumber("+998901234567"), now=NOW
    )


# --- factories -------------------------------------------------------------------------------


def test_register_via_phone_creates_active_account_with_verified_phone_method() -> None:
    account = _new_account()
    assert account.status is AccountStatus.ACTIVE
    method = account.authentication_method(AuthMethodType.PHONE_OTP)
    assert method.verified_at == NOW


def test_register_via_email_creates_active_account_with_unverified_email_method() -> None:
    account = UserAccount.register_via_email(
        account_id=UserId(value=uuid4()),
        email=EmailAddress("test@example.com"),
        password_hash="hashed:secret",
        display_name="Test User",
        now=NOW,
    )
    assert account.status is AccountStatus.ACTIVE
    method = account.authentication_method(AuthMethodType.EMAIL)
    assert method.verified_at is None
    assert method.password_hash == "hashed:secret"


def test_register_via_google_creates_active_account_with_verified_google_method() -> None:
    account = UserAccount.register_via_google(
        account_id=UserId(value=uuid4()),
        email=EmailAddress("test@example.com"),
        google_subject="google-subject-1",
        display_name="Test User",
        now=NOW,
    )
    method = account.authentication_method(AuthMethodType.GOOGLE)
    assert method.verified_at == NOW
    assert method.identifier == "google-subject-1"


def test_link_google_identity_adds_method_to_existing_account_without_duplicating() -> None:
    account = UserAccount.register_via_email(
        account_id=UserId(value=uuid4()),
        email=EmailAddress("test@example.com"),
        password_hash="hashed:secret",
        display_name=None,
        now=NOW,
    )
    linked = account.link_google_identity(google_subject="google-subject-1", now=NOW)
    assert linked.has_authentication_method(AuthMethodType.GOOGLE)
    assert len(linked.authentication_methods) == 2

    linked_again = linked.link_google_identity(google_subject="google-subject-1", now=NOW)
    assert len(linked_again.authentication_methods) == 2  # I-09: link, never duplicate


def test_authentication_method_raises_for_missing_method_type() -> None:
    account = _new_account()
    with pytest.raises(UnknownAuthenticationMethodError):
        account.authentication_method(AuthMethodType.EMAIL)


# --- profile/preferences (FR-USER-001, FR-USER-003) -------------------------------------------


def test_update_profile_changes_display_name_and_email() -> None:
    account = _new_account()
    updated = account.update_profile(
        display_name="New Name", email=EmailAddress("new@example.com"), now=NOW
    )
    assert updated.display_name == "New Name"
    assert updated.email == EmailAddress("new@example.com")


def test_update_profile_email_change_resets_email_method_verification() -> None:
    account = UserAccount.register_via_email(
        account_id=UserId(value=uuid4()),
        email=EmailAddress("old@example.com"),
        password_hash="hashed:secret",
        display_name=None,
        now=NOW,
    )
    # No use case in this task ever sets verified_at (see AuthenticationMethod's docstring) --
    # simulate a verified method directly to prove update_profile resets it on a real change.
    from dataclasses import replace

    verified_account = replace(
        account,
        authentication_methods=tuple(
            replace(m, verified_at=NOW) for m in account.authentication_methods
        ),
    )
    updated = verified_account.update_profile(
        display_name=None, email=EmailAddress("new@example.com"), now=NOW
    )
    method = updated.authentication_method(AuthMethodType.EMAIL)
    assert method.identifier == "new@example.com"
    assert method.verified_at is None


def test_update_preferences_changes_privacy_settings() -> None:
    account = _new_account()
    updated = account.update_preferences(
        privacy_settings=PrivacySettings(phone_reveal_mode=PhoneRevealMode.NEVER),
        notification_preferences=None,
        now=NOW,
    )
    assert updated.privacy_settings.phone_reveal_mode is PhoneRevealMode.NEVER


def test_change_password_requires_email_method() -> None:
    account = _new_account()
    with pytest.raises(UnknownAuthenticationMethodError):
        account.change_password(new_password_hash="hashed:new", now=NOW)


def test_change_password_replaces_hash() -> None:
    account = UserAccount.register_via_email(
        account_id=UserId(value=uuid4()),
        email=EmailAddress("test@example.com"),
        password_hash="hashed:old",
        display_name=None,
        now=NOW,
    )
    updated = account.change_password(new_password_hash="hashed:new", now=NOW)
    assert updated.authentication_method(AuthMethodType.EMAIL).password_hash == "hashed:new"


# --- lifecycle (Active <-> Suspended -> Closed) ------------------------------------------------


def test_require_active_passes_for_active_account() -> None:
    _new_account().require_active()  # does not raise


def test_require_active_raises_for_suspended_account() -> None:
    account = _new_account().suspend(now=NOW)
    with pytest.raises(AccountNotActiveError):
        account.require_active()


def test_suspend_transitions_active_to_suspended() -> None:
    account = _new_account().suspend(now=NOW)
    assert account.status is AccountStatus.SUSPENDED


def test_suspend_twice_raises_illegal_transition() -> None:
    account = _new_account().suspend(now=NOW)
    with pytest.raises(IllegalAccountStateTransitionError):
        account.suspend(now=NOW)


def test_reactivate_transitions_suspended_to_active() -> None:
    account = _new_account().suspend(now=NOW).reactivate(now=NOW)
    assert account.status is AccountStatus.ACTIVE


def test_reactivate_active_account_raises_illegal_transition() -> None:
    account = _new_account()
    with pytest.raises(IllegalAccountStateTransitionError):
        account.reactivate(now=NOW)


def test_close_anonymises_pii_and_sets_closed_status() -> None:
    account = UserAccount.register_via_phone(
        account_id=UserId(value=uuid4()), phone=PhoneNumber("+998901234567"), now=NOW
    )
    account = account.update_profile(display_name="Real Name", email=None, now=NOW)
    closed = account.close(now=NOW)
    assert closed.status is AccountStatus.CLOSED
    assert closed.phone is None
    assert closed.email is None
    assert closed.display_name is None
    assert all(
        m.identifier == "" and m.password_hash is None for m in closed.authentication_methods
    )


def test_close_from_suspended_also_allowed() -> None:
    account = _new_account().suspend(now=NOW)
    closed = account.close(now=NOW)
    assert closed.status is AccountStatus.CLOSED


def test_close_already_closed_raises_illegal_transition() -> None:
    account = _new_account().close(now=NOW)
    with pytest.raises(IllegalAccountStateTransitionError):
        account.close(now=NOW)


# --- multi-profile acting-context (FR-USER-002) -------------------------------------------------


def test_owns_profile_true_only_for_owned_profile_ids() -> None:
    from dataclasses import replace

    profile_a = BusinessProfileId(value=uuid4())
    profile_b = BusinessProfileId(value=uuid4())
    account = replace(_new_account(), owned_profile_ids=(profile_a,))
    assert account.owns_profile(profile_a) is True
    assert account.owns_profile(profile_b) is False


# --- role assignment (Config Framework Sec 7.2) -------------------------------------------------


def test_assign_role_adds_role_assignment() -> None:
    account = _new_account()
    head_id, version_id, actor = uuid4(), uuid4(), uuid4()
    updated = account.assign_role(
        role_definition_head_id=head_id,
        role_definition_version_id=version_id,
        role_code="administrator",
        acting_profile_id=None,
        assigned_by=actor,
        now=NOW,
    )
    assert len(updated.role_assignments) == 1
    assert updated.role_assignments[0].role_code == "administrator"


def test_assign_role_reassignment_supersedes_prior_pin_same_scope() -> None:
    account = _new_account()
    head_id, actor = uuid4(), uuid4()
    once = account.assign_role(
        role_definition_head_id=head_id,
        role_definition_version_id=uuid4(),
        role_code="administrator",
        acting_profile_id=None,
        assigned_by=actor,
        now=NOW,
    )
    new_version_id = uuid4()
    twice = once.assign_role(
        role_definition_head_id=head_id,
        role_definition_version_id=new_version_id,
        role_code="administrator",
        acting_profile_id=None,
        assigned_by=actor,
        now=NOW,
    )
    assert len(twice.role_assignments) == 1
    assert twice.role_assignments[0].role_definition_version_id == new_version_id


def test_revoke_role_removes_matching_assignment() -> None:
    account = _new_account()
    head_id, actor = uuid4(), uuid4()
    assigned = account.assign_role(
        role_definition_head_id=head_id,
        role_definition_version_id=uuid4(),
        role_code="administrator",
        acting_profile_id=None,
        assigned_by=actor,
        now=NOW,
    )
    revoked = assigned.revoke_role(role_definition_head_id=head_id, acting_profile_id=None, now=NOW)
    assert revoked.role_assignments == ()


def test_revoke_role_not_assigned_raises() -> None:
    account = _new_account()
    with pytest.raises(RoleNotAssignedError):
        account.revoke_role(role_definition_head_id=uuid4(), acting_profile_id=None, now=NOW)


def test_role_assignments_for_scope_includes_global_and_matching_profile_only() -> None:
    account = _new_account()
    profile_a = BusinessProfileId(value=uuid4())
    profile_b = BusinessProfileId(value=uuid4())
    actor = uuid4()
    account = account.assign_role(
        role_definition_head_id=uuid4(),
        role_definition_version_id=uuid4(),
        role_code="global-role",
        acting_profile_id=None,
        assigned_by=actor,
        now=NOW,
    )
    account = account.assign_role(
        role_definition_head_id=uuid4(),
        role_definition_version_id=uuid4(),
        role_code="profile-a-role",
        acting_profile_id=profile_a,
        assigned_by=actor,
        now=NOW,
    )
    account = account.assign_role(
        role_definition_head_id=uuid4(),
        role_definition_version_id=uuid4(),
        role_code="profile-b-role",
        acting_profile_id=profile_b,
        assigned_by=actor,
        now=NOW,
    )

    for_a = account.role_assignments_for_scope(profile_a)
    codes_a = {ra.role_code for ra in for_a}
    assert codes_a == {"global-role", "profile-a-role"}

    for_personal = account.role_assignments_for_scope(None)
    codes_personal = {ra.role_code for ra in for_personal}
    assert codes_personal == {"global-role"}


# --- ADR-0007 account_kind / registration review --------------------------------------------


def test_register_via_phone_legal_entity_starts_pending_review() -> None:
    """`_initial_review_status`: only INDIVIDUAL skips review -- LEGAL_ENTITY/INVESTOR need a
    reviewer decision before their workspace unlocks."""
    account = UserAccount.register_via_phone(
        account_id=UserId(value=uuid4()),
        phone=PhoneNumber("+998901234567"),
        now=NOW,
        account_kind=AccountKind.LEGAL_ENTITY,
    )
    assert account.review_status is RegistrationReviewStatus.PENDING


def test_register_via_email_individual_starts_approved_review() -> None:
    account = UserAccount.register_via_email(
        account_id=UserId(value=uuid4()),
        email=EmailAddress("individual@example.com"),
        password_hash="hashed:secret",
        display_name=None,
        now=NOW,
        account_kind=AccountKind.INDIVIDUAL,
    )
    assert account.review_status is RegistrationReviewStatus.APPROVED


def test_decide_registration_approved_sets_status_and_decision() -> None:
    account = UserAccount.register_via_phone(
        account_id=UserId(value=uuid4()),
        phone=PhoneNumber("+998901234567"),
        now=NOW,
        account_kind=AccountKind.LEGAL_ENTITY,
    )
    reviewer_id = uuid4()
    decided = account.decide_registration(
        outcome=RegistrationReviewStatus.APPROVED,
        reason=None,
        reviewer_user_id=reviewer_id,
        now=NOW,
    )
    assert decided.review_status is RegistrationReviewStatus.APPROVED
    assert decided.review_decision is not None
    assert decided.review_decision.outcome is RegistrationReviewStatus.APPROVED
    assert decided.review_decision.reviewer_user_id == reviewer_id


def test_decide_registration_rejected_sets_status_and_reason() -> None:
    account = UserAccount.register_via_phone(
        account_id=UserId(value=uuid4()),
        phone=PhoneNumber("+998901234567"),
        now=NOW,
        account_kind=AccountKind.INVESTOR,
    )
    decided = account.decide_registration(
        outcome=RegistrationReviewStatus.REJECTED,
        reason="incomplete anketa",
        reviewer_user_id=uuid4(),
        now=NOW,
    )
    assert decided.review_status is RegistrationReviewStatus.REJECTED
    assert decided.review_decision is not None
    assert decided.review_decision.reason == "incomplete anketa"


def test_decide_registration_already_decided_raises() -> None:
    account = UserAccount.register_via_phone(
        account_id=UserId(value=uuid4()),
        phone=PhoneNumber("+998901234567"),
        now=NOW,
        account_kind=AccountKind.LEGAL_ENTITY,
    ).decide_registration(
        outcome=RegistrationReviewStatus.APPROVED, reason=None, reviewer_user_id=uuid4(), now=NOW
    )
    with pytest.raises(RegistrationAlreadyDecidedError):
        account.decide_registration(
            outcome=RegistrationReviewStatus.REJECTED,
            reason=None,
            reviewer_user_id=uuid4(),
            now=NOW,
        )


# --- federated identity (Apple) / phone linking ----------------------------------------------


def test_register_via_apple_creates_active_account_with_verified_apple_method() -> None:
    account = UserAccount.register_via_apple(
        account_id=UserId(value=uuid4()),
        email=EmailAddress("apple-user@example.com"),
        apple_subject="apple-subject-1",
        display_name="Apple User",
        now=NOW,
    )
    assert account.status is AccountStatus.ACTIVE
    method = account.authentication_method(AuthMethodType.APPLE)
    assert method.verified_at == NOW
    assert method.identifier == "apple-subject-1"


def test_link_apple_identity_adds_method_to_existing_account_without_duplicating() -> None:
    account = UserAccount.register_via_email(
        account_id=UserId(value=uuid4()),
        email=EmailAddress("apple-user@example.com"),
        password_hash="hashed:secret",
        display_name=None,
        now=NOW,
    )
    linked = account.link_apple_identity(apple_subject="apple-subject-1", now=NOW)
    assert linked.has_authentication_method(AuthMethodType.APPLE)
    assert len(linked.authentication_methods) == 2

    linked_again = linked.link_apple_identity(apple_subject="apple-subject-1", now=NOW)
    assert len(linked_again.authentication_methods) == 2  # I-09: link, never duplicate


def test_link_phone_attaches_verified_phone_to_account_without_one() -> None:
    account = UserAccount.register_via_email(
        account_id=UserId(value=uuid4()),
        email=EmailAddress("no-phone@example.com"),
        password_hash="hashed:secret",
        display_name=None,
        now=NOW,
    )
    linked = account.link_phone(phone=PhoneNumber("+998901234567"), now=NOW)
    assert linked.phone == PhoneNumber("+998901234567")
    assert linked.has_authentication_method(AuthMethodType.PHONE_OTP)


def test_link_phone_replaces_prior_phone_method() -> None:
    account = _new_account()  # already has +998901234567 via PHONE_OTP
    relinked = account.link_phone(phone=PhoneNumber("+998907654321"), now=NOW)
    assert relinked.phone == PhoneNumber("+998907654321")
    phone_methods = [
        m for m in relinked.authentication_methods if m.method_type is AuthMethodType.PHONE_OTP
    ]
    assert len(phone_methods) == 1
    assert phone_methods[0].identifier == "+998907654321"


def test_link_phone_same_number_already_linked_is_a_no_op() -> None:
    account = _new_account()  # already linked to +998901234567
    relinked = account.link_phone(phone=PhoneNumber("+998901234567"), now=NOW)
    assert relinked == account


# --- multi-profile acting-context (FR-USER-002) -----------------------------------------------


def test_link_owned_profile_adds_profile_id() -> None:
    account = _new_account()
    profile_id = BusinessProfileId(value=uuid4())
    linked = account.link_owned_profile(profile_id=profile_id, now=NOW)
    assert linked.owns_profile(profile_id)


def test_link_owned_profile_already_owned_is_idempotent() -> None:
    account = _new_account()
    profile_id = BusinessProfileId(value=uuid4())
    linked = account.link_owned_profile(profile_id=profile_id, now=NOW)
    linked_again = linked.link_owned_profile(profile_id=profile_id, now=NOW)
    assert linked_again == linked
    assert linked_again.owned_profile_ids.count(profile_id) == 1
