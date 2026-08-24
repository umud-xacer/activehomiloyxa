"""identity -- DTOs (Task P-01). Translated field-for-field from the OpenAPI
operations tagged to this module (contracts/openapi.yaml). Schema only: no aggregate
type is exposed here, no business behaviour, no validation beyond what Pydantic
itself does structurally.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from active_home_shared import CamelModel


class PageInfo(CamelModel):
    """Cursor pagination metadata (OpenAPI `CursorPage.page`)."""

    limit: int
    next_cursor: str | None = None
    """Pass as `cursor` to fetch the next page; null when exhausted."""
    total: int | None = None
    """Present only where cheap to compute; may be null."""


class UserStatusChangeRequest(CamelModel):
    """OpenAPI `UserStatusChangeRequest`."""

    action: Literal["SUSPEND", "REACTIVATE", "CLOSE"]
    reason: str | None = None


class RoleAssignmentRequest(CamelModel):
    """OpenAPI `RoleAssignmentRequest` (ADR-0006)."""

    role_code: str
    acting_profile_id: UUID | None = None
    """Null scopes the role to the account's personal acting context; a concrete id scopes it to
    that one owned business profile only (I-10)."""


class UserAdminView(CamelModel):
    """OpenAPI `UserAdminView`."""

    id: UUID
    phone_number: str | None = None
    email: str | None = None
    status: Literal["ACTIVE", "SUSPENDED", "CLOSED"]
    created_at: datetime | None = None
    owned_profile_ids: list[UUID] | None = None
    """2026-08-24: which business profile(s) this account owns, if any -- lets `/admin/users`
    link to the same profile's billing credit balance without a second lookup. `None`/empty for
    an INDIVIDUAL account or a LEGAL_ENTITY that never completed onboarding."""


class UserAdminViewPage(CamelModel):
    """A cursor-paginated page of `UserAdminView` (OpenAPI `CursorPage` composed with
    `items: UserAdminView[]` via `allOf`)."""

    items: list[UserAdminView]
    page: PageInfo


class PasswordChangeRequest(CamelModel):
    """OpenAPI `PasswordChangeRequest`."""

    current_password: str
    new_password: str


class Account(CamelModel):
    """The authenticated user's own account (BC-01 UserAccount)."""

    id: UUID
    phone_number: str | None = None
    """E.164; null after anonymisation."""
    email: str | None = None
    display_name: str | None = None
    status: Literal["ACTIVE", "SUSPENDED", "CLOSED"]
    privacy_settings: PrivacySettings | None = None
    notification_preferences: NotificationPreferences | None = None
    owned_profile_ids: list[UUID] | None = None
    roles: list[str] | None = None
    created_at: datetime
    account_kind: Literal["INDIVIDUAL", "LEGAL_ENTITY", "INVESTOR"] | None = None
    """ADR-0007: the role chosen at signup."""
    review_status: Literal["PENDING", "APPROVED", "REJECTED"] | None = None
    """ADR-0007: gates the role-specific workspace (login itself is unaffected -- governed by
    `status` as before)."""
    review_reason: str | None = None
    """The reviewer's note, populated once `review_status` is APPROVED/REJECTED."""


class PrivacySettings(CamelModel):
    """OpenAPI `PrivacySettings`."""

    phone_reveal_mode: Literal["ALWAYS", "ON_REQUEST", "NEVER"] | None = "ON_REQUEST"
    """BRULE-13 phone-reveal gating."""


class NotificationPreferences(CamelModel):
    """Channel opt-ins by category. OTP is always delivered via SMS (Eskiz) regardless of
    preference."""

    email: bool | None = True
    web_push: bool | None = False
    sms: bool | None = True


class Session(CamelModel):
    """An authenticated session (BC-01 Session)."""

    id: UUID
    acting_profile_id: UUID | None = None
    """null = personal context."""
    ip_address: str | None = None
    user_agent: str | None = None
    current: bool | None = None
    """True for the session making this request."""
    created_at: datetime
    expires_at: datetime


class LoginEmailRequest(CamelModel):
    """OpenAPI `LoginEmailRequest`."""

    email: str
    password: str


class SessionEstablished(CamelModel):
    """Returned by any successful auth flow. For browsers the session is also set as the
    `ah_session` cookie; `sessionToken` is returned for native/mobile clients using the Bearer
    scheme."""

    account: Account
    session: Session
    session_token: str | None = None
    """Opaque session reference for Bearer clients. Null/omitted when only the cookie is issued."""


class GoogleSignInRequest(CamelModel):
    """OpenAPI `GoogleSignInRequest`."""

    authorization_code: str
    """Google authorization-code from the client flow."""
    redirect_uri: str


class AppleSignInRequest(CamelModel):
    """OpenAPI `AppleSignInRequest`. Mirrors `GoogleSignInRequest`."""

    authorization_code: str
    """Apple authorization-code from the client flow."""
    redirect_uri: str


class PhoneLinkRequest(CamelModel):
    """OpenAPI `PhoneLinkRequest`. Requests an OTP to attach a phone to the *authenticated*
    account -- distinct from `OtpRequest`, which is anonymous/pre-auth and never accepts
    LINK_PHONE as a purpose."""

    phone_number: str


class PhoneLinkVerifyRequest(CamelModel):
    """OpenAPI `PhoneLinkVerifyRequest`."""

    phone_number: str
    code: str


class RegisterEmailRequest(CamelModel):
    """OpenAPI `RegisterEmailRequest`."""

    email: str
    password: str
    display_name: str | None = None
    account_kind: Literal["INDIVIDUAL", "LEGAL_ENTITY", "INVESTOR"] = "INDIVIDUAL"
    """ADR-0007: the role chosen in the sign-up wizard's first step."""
    anketa: dict[str, object] | None = None
    """ADR-0007: the role-specific questionnaire answers from the wizard's second step. Freeform
    -- shape depends on `account_kind` (mirrors `BusinessProfile.contacts`'s own "no fixed
    schema" pattern)."""


class OtpRequest(CamelModel):
    """OpenAPI `OtpRequest`."""

    phone_number: str
    purpose: Literal["REGISTRATION", "LOGIN", "RECOVERY"]


class RecoveryStartRequest(CamelModel):
    """Start account recovery via a verified phone or email."""

    phone_number: str | None = None
    email: str | None = None


class SwitchActingProfileBody(CamelModel):
    """OpenAPI `SwitchActingProfileBody`."""

    acting_profile_id: UUID | None = None
    """null = personal context."""


class UpdateMeBody(CamelModel):
    """OpenAPI `UpdateMeBody`."""

    display_name: str | None = None
    email: str | None = None


class UpdatePreferencesBody(CamelModel):
    """OpenAPI `UpdatePreferencesBody`."""

    privacy_settings: PrivacySettings | None = None
    notification_preferences: NotificationPreferences | None = None


class OtpVerifyRequest(CamelModel):
    """OpenAPI `OtpVerifyRequest`."""

    phone_number: str
    code: str
    purpose: Literal["REGISTRATION", "LOGIN", "RECOVERY"]
    account_kind: Literal["INDIVIDUAL", "LEGAL_ENTITY", "INVESTOR"] = "INDIVIDUAL"
    """ADR-0007: only consulted when `purpose=REGISTRATION` and no account exists yet for this
    phone -- ignored otherwise (see `AuthenticationUseCases.verify_otp`)."""
    anketa: dict[str, object] | None = None
    """ADR-0007: see `RegisterEmailRequest.anketa`."""


class RegistrationDecisionRequest(CamelModel):
    """OpenAPI `RegistrationDecisionRequest` (ADR-0007) -- mirrors `VerificationDecisionRequest`."""

    outcome: Literal["APPROVED", "REJECTED"]
    reason: str | None = None


class RegistrationQueueItem(CamelModel):
    """OpenAPI `RegistrationQueueItem` (ADR-0007) -- a PENDING account as the reviewer needs to
    see it: enough identity to contact the applicant, plus their full anketa."""

    id: UUID
    phone_number: str | None = None
    email: str | None = None
    display_name: str | None = None
    account_kind: Literal["INDIVIDUAL", "LEGAL_ENTITY", "INVESTOR"]
    anketa: dict[str, object]
    created_at: datetime


class RegistrationQueuePage(CamelModel):
    """A cursor-paginated page of `RegistrationQueueItem` (OpenAPI `CursorPage` composed with
    `items: RegistrationQueueItem[]` via `allOf`)."""

    items: list[RegistrationQueueItem]
    page: PageInfo
