"""identity -- the UserAccount aggregate (DDD Sec 5.1). Persistence-ignorant (mirrors
`configuration.domain.head_version`'s style): frozen dataclasses, every state transition returns
a new instance via `dataclasses.replace`, guarded by a typed exception raised before the
replace. `AuthenticationMethod` and `RoleAssignment` are entities *inside* this aggregate's
boundary, not separate aggregate roots -- DDD Sec 5.1 lists `RoleAssignment [C-ref]` as an entity
of `UserAccount` ("references a configured Role"), so one repository/one transaction covers
account state, its authentication methods, and its role assignments together (Clean
Architecture rule: one aggregate = one repository = one work unit).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from uuid import UUID

from identity.domain.exceptions import (
    AccountNotActiveError,
    IllegalAccountStateTransitionError,
    RegistrationAlreadyDecidedError,
    RoleNotAssignedError,
    UnknownAuthenticationMethodError,
)
from identity.domain.value_objects import (
    AccountKind,
    AccountStatus,
    AuthMethodType,
    EmailAddress,
    NotificationPreferences,
    PhoneNumber,
    PrivacySettings,
    RegistrationDecision,
    RegistrationReviewStatus,
)
from shared_kernel import BusinessProfileId, UserId


@dataclass(frozen=True)
class AuthenticationMethod:
    """DDD Sec 5.1: "one per channel: PhoneOtp, EmailCredential, GoogleFederated". `identifier`
    is the phone E.164 string, lower-cased email, or opaque Google subject id depending on
    `method_type`. `password_hash` is populated for EMAIL only (Argon2id, Security Sec 3.1) --
    infrastructure/'s adapter hashes it; domain never sees a plaintext password.

    `verified_at` records email confirmation for traceability. No use case in this task can ever
    set it after `added_at=None` for EMAIL (contracts/openapi.yaml has no confirm-email
    operation to consume a confirmation token against -- flagged as an architecture gap for a
    future ADR in identity/README.md); PHONE_OTP and GOOGLE are always verified at creation
    (OTP possession / Google's own email-verified claim)."""

    method_type: AuthMethodType
    identifier: str
    verified_at: datetime | None
    added_at: datetime
    password_hash: str | None = None


@dataclass(frozen=True)
class RoleAssignment:
    """DDD Sec 5.1 entity: "RoleAssignment [C-ref] (references a configured Role)". Pins the
    identity + the exact published RoleDefinition version at assignment time (Config Framework
    Sec 7.2: "Role assignments pin identity + role version in BC-01") -- reassignment is required
    to pick up a newer published version, there is no live pointer to "current".

    `acting_profile_id=None` scopes the role to the account's personal acting context; a
    concrete id scopes it to that one owned business profile only (I-10 per-acting-profile
    scoping: a role granted under one acting profile must not leak into another)."""

    role_definition_head_id: UUID
    role_definition_version_id: UUID
    role_code: str
    acting_profile_id: BusinessProfileId | None
    assigned_at: datetime
    assigned_by: UUID


@dataclass(frozen=True)
class UserAccount:
    """DDD Sec 5.1 aggregate root `UserAccount [P]`. `lock_version` matches
    `backbone.persistence.AggregateMixin`'s optimistic-locking column."""

    id: UserId
    phone: PhoneNumber | None
    email: EmailAddress | None
    display_name: str | None
    status: AccountStatus
    privacy_settings: PrivacySettings
    notification_preferences: NotificationPreferences
    owned_profile_ids: tuple[BusinessProfileId, ...]
    authentication_methods: tuple[AuthenticationMethod, ...]
    role_assignments: tuple[RoleAssignment, ...]
    created_at: datetime
    updated_at: datetime
    account_kind: AccountKind = AccountKind.INDIVIDUAL
    """ADR-0007: the role chosen at signup. Defaults to INDIVIDUAL only for aggregates built
    before this field existed (backfilled migration) -- every registration factory below always
    passes it explicitly."""
    anketa: dict[str, object] = field(default_factory=dict)
    """ADR-0007: freeform per-`account_kind` signup questionnaire answers, mirrors
    `profiles.BusinessProfile.contacts`'s "freeform JSONB, no fixed shape" pattern."""
    review_status: RegistrationReviewStatus = RegistrationReviewStatus.PENDING
    """ADR-0007: gates the role-specific workspace only -- orthogonal to `status`
    (AccountStatus), which continues to govern login as it always has."""
    review_decision: RegistrationDecision | None = None
    lock_version: int = 0

    # --- factories (I-09: uniqueness is enforced by the calling use case via the repository;
    # these factories only shape a fresh, internally-consistent aggregate) -----------------

    @staticmethod
    def register_via_phone(
        *,
        account_id: UserId,
        phone: PhoneNumber,
        now: datetime,
        account_kind: AccountKind = AccountKind.INDIVIDUAL,
        anketa: dict[str, object] | None = None,
    ) -> UserAccount:
        """FR-AUTH-001: registration via a verified phone OTP. The OTP has already been verified
        by the caller (`OtpChallenge.verify`) before this factory runs, so the method is
        recorded as verified immediately. ADR-0007: `account_kind`/`anketa` are captured at the
        same signup step (registration wizard's role-picker + questionnaire); `review_status`
        always starts `PENDING` regardless of `account_kind` -- every new account, individual
        included, waits for a reviewer decision before its workspace unlocks."""
        method = AuthenticationMethod(
            method_type=AuthMethodType.PHONE_OTP,
            identifier=phone.value,
            verified_at=now,
            added_at=now,
        )
        return UserAccount(
            id=account_id,
            phone=phone,
            email=None,
            display_name=None,
            status=AccountStatus.ACTIVE,
            privacy_settings=PrivacySettings(),
            notification_preferences=NotificationPreferences(),
            owned_profile_ids=(),
            authentication_methods=(method,),
            role_assignments=(),
            created_at=now,
            updated_at=now,
            account_kind=account_kind,
            anketa=dict(anketa) if anketa else {},
            review_status=RegistrationReviewStatus.PENDING,
        )

    @staticmethod
    def register_via_email(
        *,
        account_id: UserId,
        email: EmailAddress,
        password_hash: str,
        display_name: str | None,
        now: datetime,
        account_kind: AccountKind = AccountKind.INDIVIDUAL,
        anketa: dict[str, object] | None = None,
    ) -> UserAccount:
        """FR-AUTH-002. `AccountStatus` has no PENDING value in the frozen contract, so the
        account is ACTIVE immediately; `verified_at=None` on the EMAIL method records that
        confirmation has not been completed (see `AuthenticationMethod` docstring). ADR-0007:
        `review_status` starts `PENDING` regardless of `account_kind` -- see `register_via_phone`."""
        method = AuthenticationMethod(
            method_type=AuthMethodType.EMAIL,
            identifier=email.value,
            verified_at=None,
            added_at=now,
            password_hash=password_hash,
        )
        return UserAccount(
            id=account_id,
            phone=None,
            email=email,
            display_name=display_name,
            status=AccountStatus.ACTIVE,
            privacy_settings=PrivacySettings(),
            notification_preferences=NotificationPreferences(),
            owned_profile_ids=(),
            authentication_methods=(method,),
            role_assignments=(),
            created_at=now,
            updated_at=now,
            account_kind=account_kind,
            anketa=dict(anketa) if anketa else {},
            review_status=RegistrationReviewStatus.PENDING,
        )

    @staticmethod
    def register_via_google(
        *,
        account_id: UserId,
        email: EmailAddress,
        google_subject: str,
        display_name: str | None,
        now: datetime,
        account_kind: AccountKind = AccountKind.INDIVIDUAL,
        anketa: dict[str, object] | None = None,
    ) -> UserAccount:
        """FR-AUTH-003, first sign-in with no pre-existing account for this verified email. Only
        called when the caller's repository lookup found no existing account with this email --
        otherwise `link_google_identity` is used instead (I-09: link, never duplicate). ADR-0007:
        `review_status` starts `PENDING` regardless of `account_kind` -- see `register_via_phone`."""
        method = AuthenticationMethod(
            method_type=AuthMethodType.GOOGLE,
            identifier=google_subject,
            verified_at=now,
            added_at=now,
        )
        return UserAccount(
            id=account_id,
            phone=None,
            email=email,
            display_name=display_name,
            status=AccountStatus.ACTIVE,
            privacy_settings=PrivacySettings(),
            notification_preferences=NotificationPreferences(),
            owned_profile_ids=(),
            authentication_methods=(method,),
            role_assignments=(),
            created_at=now,
            updated_at=now,
            account_kind=account_kind,
            anketa=dict(anketa) if anketa else {},
            review_status=RegistrationReviewStatus.PENDING,
        )

    def link_google_identity(self, *, google_subject: str, now: datetime) -> UserAccount:
        """I-09 / FR-AUTH-003 acceptance 2: "an existing account with the same verified email is
        linked, not duplicated." Adds a GOOGLE authentication method to this existing account
        instead of creating a new one."""
        if any(m.method_type is AuthMethodType.GOOGLE for m in self.authentication_methods):
            return self
        method = AuthenticationMethod(
            method_type=AuthMethodType.GOOGLE,
            identifier=google_subject,
            verified_at=now,
            added_at=now,
        )
        return replace(
            self, authentication_methods=(*self.authentication_methods, method), updated_at=now
        )

    @staticmethod
    def register_via_apple(
        *,
        account_id: UserId,
        email: EmailAddress,
        apple_subject: str,
        display_name: str | None,
        now: datetime,
        account_kind: AccountKind = AccountKind.INDIVIDUAL,
        anketa: dict[str, object] | None = None,
    ) -> UserAccount:
        """Sign in with Apple, mirrors `register_via_google` exactly -- same FR-AUTH-003-style
        federated-identity shape, only the provider differs. Only called when the caller's
        repository lookup found no existing account with this verified email (I-09: link, never
        duplicate; `link_apple_identity` handles the existing-account case)."""
        method = AuthenticationMethod(
            method_type=AuthMethodType.APPLE,
            identifier=apple_subject,
            verified_at=now,
            added_at=now,
        )
        return UserAccount(
            id=account_id,
            phone=None,
            email=email,
            display_name=display_name,
            status=AccountStatus.ACTIVE,
            privacy_settings=PrivacySettings(),
            notification_preferences=NotificationPreferences(),
            owned_profile_ids=(),
            authentication_methods=(method,),
            role_assignments=(),
            created_at=now,
            updated_at=now,
            account_kind=account_kind,
            anketa=dict(anketa) if anketa else {},
            review_status=RegistrationReviewStatus.PENDING,
        )

    def link_apple_identity(self, *, apple_subject: str, now: datetime) -> UserAccount:
        """I-09, mirrors `link_google_identity`: adds an APPLE authentication method to this
        existing (matched-by-verified-email) account instead of creating a new one."""
        if any(m.method_type is AuthMethodType.APPLE for m in self.authentication_methods):
            return self
        method = AuthenticationMethod(
            method_type=AuthMethodType.APPLE,
            identifier=apple_subject,
            verified_at=now,
            added_at=now,
        )
        return replace(
            self, authentication_methods=(*self.authentication_methods, method), updated_at=now
        )

    def link_phone(self, *, phone: PhoneNumber, now: datetime) -> UserAccount:
        """Attaches a verified phone number to an account that didn't register with one (e.g. an
        email/Google/Apple signup) -- the OTP has already been verified by the caller (mirrors
        `register_via_phone`'s own "verified before this runs" contract) against the candidate
        phone's ownership, not this account's identity, so uniqueness (one phone -> one account)
        is the calling use case's job via the repository (I-09), same division of responsibility
        as every other duplicate-contact check in this module. A no-op if this exact phone is
        already the account's own linked number (idempotent from the caller's perspective, same
        shape as `link_google_identity`)."""
        if self.phone == phone and self.has_authentication_method(AuthMethodType.PHONE_OTP):
            return self
        method = AuthenticationMethod(
            method_type=AuthMethodType.PHONE_OTP,
            identifier=phone.value,
            verified_at=now,
            added_at=now,
        )
        methods = tuple(
            m for m in self.authentication_methods if m.method_type != AuthMethodType.PHONE_OTP
        )
        return replace(
            self,
            phone=phone,
            authentication_methods=(*methods, method),
            updated_at=now,
        )

    # --- authentication method lookups ------------------------------------------------------

    def authentication_method(self, method_type: AuthMethodType) -> AuthenticationMethod:
        for method in self.authentication_methods:
            if method.method_type is method_type:
                return method
        raise UnknownAuthenticationMethodError(method_type.value)

    def has_authentication_method(self, method_type: AuthMethodType) -> bool:
        return any(m.method_type is method_type for m in self.authentication_methods)

    # --- profile/preferences (FR-USER-001, FR-USER-003) --------------------------------------

    def update_profile(
        self, *, display_name: str | None, email: EmailAddress | None, now: datetime
    ) -> UserAccount:
        """FR-USER-001. Changing the email also updates the EMAIL authentication method's
        identifier and resets its `verified_at` (a changed address has not been reconfirmed)."""
        account = replace(self, display_name=display_name, updated_at=now)
        if email is not None and email != self.email:
            account = replace(account, email=email)
            if self.has_authentication_method(AuthMethodType.EMAIL):
                methods = tuple(
                    replace(m, identifier=email.value, verified_at=None)
                    if m.method_type is AuthMethodType.EMAIL
                    else m
                    for m in account.authentication_methods
                )
                account = replace(account, authentication_methods=methods)
        return account

    def update_preferences(
        self,
        *,
        privacy_settings: PrivacySettings | None,
        notification_preferences: NotificationPreferences | None,
        now: datetime,
    ) -> UserAccount:
        """FR-USER-003 (BRULE-13 phone-reveal mode) + notification channel opt-ins."""
        return replace(
            self,
            privacy_settings=privacy_settings
            if privacy_settings is not None
            else self.privacy_settings,
            notification_preferences=(
                notification_preferences
                if notification_preferences is not None
                else self.notification_preferences
            ),
            updated_at=now,
        )

    def change_password(self, *, new_password_hash: str, now: datetime) -> UserAccount:
        if not self.has_authentication_method(AuthMethodType.EMAIL):
            raise UnknownAuthenticationMethodError(AuthMethodType.EMAIL.value)
        methods = tuple(
            replace(m, password_hash=new_password_hash)
            if m.method_type is AuthMethodType.EMAIL
            else m
            for m in self.authentication_methods
        )
        return replace(self, authentication_methods=methods, updated_at=now)

    # --- lifecycle (Active <-> Suspended -> Closed, DDD Sec 5.1) ------------------------------

    def require_active(self) -> None:
        if self.status is not AccountStatus.ACTIVE:
            raise AccountNotActiveError(self.status.value)

    def suspend(self, *, now: datetime) -> UserAccount:
        if self.status is not AccountStatus.ACTIVE:
            raise IllegalAccountStateTransitionError(
                self.status.value, AccountStatus.SUSPENDED.value
            )
        return replace(self, status=AccountStatus.SUSPENDED, updated_at=now)

    def reactivate(self, *, now: datetime) -> UserAccount:
        if self.status is not AccountStatus.SUSPENDED:
            raise IllegalAccountStateTransitionError(self.status.value, AccountStatus.ACTIVE.value)
        return replace(self, status=AccountStatus.ACTIVE, updated_at=now)

    def close(self, *, now: datetime) -> UserAccount:
        """FR-USER-005 `AccountClosurePolicy`: "deactivate + initiate data handling". Closed
        means anonymised and retained, never hard-deleted -- the row (id, status, created_at,
        role_assignments for audit) survives; every PII-bearing field is cleared. Phone/email
        are nullable under the partial-unique constraints, so setting them to `None` cannot
        collide with another account."""
        if self.status is AccountStatus.CLOSED:
            raise IllegalAccountStateTransitionError(self.status.value, AccountStatus.CLOSED.value)
        anonymised_methods = tuple(
            replace(m, identifier="", password_hash=None) for m in self.authentication_methods
        )
        return replace(
            self,
            status=AccountStatus.CLOSED,
            phone=None,
            email=None,
            display_name=None,
            authentication_methods=anonymised_methods,
            updated_at=now,
        )

    # --- registration review (ADR-0007) ---------------------------------------------------------

    def decide_registration(
        self,
        *,
        outcome: RegistrationReviewStatus,
        reason: str | None,
        reviewer_user_id: UUID,
        now: datetime,
    ) -> UserAccount:
        """A reviewer approves or rejects this account's signup anketa. Only ever leaves
        `PENDING` -- APPROVED/REJECTED are terminal (mirrors `profiles.VerificationCase.decide`'s
        equivalent guard)."""
        if self.review_status is not RegistrationReviewStatus.PENDING:
            raise RegistrationAlreadyDecidedError(self.id.value, self.review_status.value)
        decision = RegistrationDecision(
            outcome=outcome, reason=reason, reviewer_user_id=reviewer_user_id, decided_at=now
        )
        return replace(self, review_status=outcome, review_decision=decision, updated_at=now)

    # --- multi-profile acting-context (FR-USER-002) -------------------------------------------

    def owns_profile(self, profile_id: BusinessProfileId) -> bool:
        return profile_id in self.owned_profile_ids

    def link_owned_profile(self, *, profile_id: BusinessProfileId, now: datetime) -> UserAccount:
        """P-20 fix (confirmed integration defect): the reaction to `profiles.BusinessProfile
        Created` that was previously missing entirely -- without it, `owned_profile_ids` never
        gained a freshly created profile, so `switch_acting_profile`/`owns_profile` could never
        legitimately recognise it (FR-USER-002 requires the account to own a profile before
        acting as it). Idempotent -- redelivery of the same event must not duplicate an entry
        (mirrors `catalog.Favorite`'s own "favoriting an already-favorited listing is a no-op"
        precedent) -- `owned_profile_ids` has no uniqueness invariant of its own to lean on."""
        if profile_id in self.owned_profile_ids:
            return self
        return replace(
            self, owned_profile_ids=(*self.owned_profile_ids, profile_id), updated_at=now
        )

    # --- role assignment (Config Framework Sec 7.2) ---------------------------------------------

    def assign_role(
        self,
        *,
        role_definition_head_id: UUID,
        role_definition_version_id: UUID,
        role_code: str,
        acting_profile_id: BusinessProfileId | None,
        assigned_by: UUID,
        now: datetime,
    ) -> UserAccount:
        """Reassignment (same head + same acting-profile scope) supersedes the prior pin rather
        than accumulating duplicates."""
        remaining = tuple(
            ra
            for ra in self.role_assignments
            if not (
                ra.role_definition_head_id == role_definition_head_id
                and ra.acting_profile_id == acting_profile_id
            )
        )
        new_assignment = RoleAssignment(
            role_definition_head_id=role_definition_head_id,
            role_definition_version_id=role_definition_version_id,
            role_code=role_code,
            acting_profile_id=acting_profile_id,
            assigned_at=now,
            assigned_by=assigned_by,
        )
        return replace(self, role_assignments=(*remaining, new_assignment), updated_at=now)

    def revoke_role(
        self,
        *,
        role_definition_head_id: UUID,
        acting_profile_id: BusinessProfileId | None,
        now: datetime,
    ) -> UserAccount:
        remaining = tuple(
            ra
            for ra in self.role_assignments
            if not (
                ra.role_definition_head_id == role_definition_head_id
                and ra.acting_profile_id == acting_profile_id
            )
        )
        if len(remaining) == len(self.role_assignments):
            raise RoleNotAssignedError(role_definition_head_id)
        return replace(self, role_assignments=remaining, updated_at=now)

    def role_assignments_for_scope(
        self, acting_profile_id: BusinessProfileId | None
    ) -> tuple[RoleAssignment, ...]:
        """I-10: the assignments that apply to a given acting context -- global (personal-scope)
        assignments always apply, plus any assignment scoped to this exact acting profile.
        Never returns another profile's assignments (the scoping boundary itself)."""
        return tuple(
            ra
            for ra in self.role_assignments
            if ra.acting_profile_id is None or ra.acting_profile_id == acting_profile_id
        )
