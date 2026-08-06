"""identity -- ports (Task P-01). Abstract surface only (typing.Protocol): no
implementation, no aggregates, no ORM types. Each method's docstring cites the
OpenAPI operationId it derives from, for traceability back to contracts/openapi.yaml.
"""

from __future__ import annotations

from typing import Literal, Protocol
from uuid import UUID

from identity.interfaces.dto import (
    Account,
    GoogleSignInRequest,
    LoginEmailRequest,
    OtpRequest,
    OtpVerifyRequest,
    PasswordChangeRequest,
    RecoveryStartRequest,
    RegisterEmailRequest,
    RoleAssignmentRequest,
    Session,
    SessionEstablished,
    SwitchActingProfileBody,
    UpdateMeBody,
    UpdatePreferencesBody,
    UserAdminView,
    UserAdminViewPage,
    UserStatusChangeRequest,
)
from shared_kernel import BusinessProfileId, UserId


class ActingIdentityQueryPort(Protocol):
    """Derived from OpenAPI operations: `adminChangeUserStatus`, `adminListUsers`, `assignRole`,
    `revokeRole` (ADR-0006), `changePassword`, `closeAccount`, `getMe`, `listSessions`,
    `revokeSession`, `switchActingProfile`, `updateMe`, `updatePreferences`."""

    async def admin_change_user_status(
        self, user_id: UUID, body: UserStatusChangeRequest
    ) -> UserAdminView:
        """`POST /admin/users/{userId}/status` (operationId `adminChangeUserStatus`). Suspend or reactivate a user"""
        ...

    async def admin_list_users(
        self,
        status: Literal["ACTIVE", "SUSPENDED", "CLOSED"] | None = None,
        query: str | None = None,
        cursor: str | None = None,
        limit: int | None = 20,
    ) -> UserAdminViewPage:
        """`GET /admin/users` (operationId `adminListUsers`). List users (admin)"""
        ...

    async def assign_role(self, user_id: UUID, body: RoleAssignmentRequest) -> UserAdminView:
        """`POST /admin/users/{userId}/roles` (operationId `assignRole`, ADR-0006). Assign a role
        to a user"""
        ...

    async def revoke_role(
        self,
        user_id: UUID,
        role_definition_head_id: UUID,
        acting_profile_id: UUID | None = None,
    ) -> UserAdminView:
        """`DELETE /admin/users/{userId}/roles/{roleDefinitionHeadId}` (operationId `revokeRole`,
        ADR-0006). Revoke a role from a user"""
        ...

    async def change_password(self, body: PasswordChangeRequest) -> None:
        """`PUT /me/password` (operationId `changePassword`). Change password"""
        ...

    async def close_account(self) -> None:
        """`DELETE /me/account` (operationId `closeAccount`). Close (anonymise) the account"""
        ...

    async def get_me(self, fields: str | None = None) -> Account:
        """`GET /me` (operationId `getMe`). Get the authenticated account"""
        ...

    async def list_sessions(self) -> list[Session]:
        """`GET /me/sessions` (operationId `listSessions`). List active sessions"""
        ...

    async def revoke_session(self, session_id: UUID) -> None:
        """`DELETE /me/sessions/{sessionId}` (operationId `revokeSession`). Revoke a session"""
        ...

    async def switch_acting_profile(self, body: SwitchActingProfileBody) -> Session:
        """`POST /me/sessions/switch-profile` (operationId `switchActingProfile`). Switch the acting profile for the current session"""
        ...

    async def update_me(self, body: UpdateMeBody) -> Account:
        """`PATCH /me` (operationId `updateMe`). Update personal profile"""
        ...

    async def update_preferences(self, body: UpdatePreferencesBody) -> Account:
        """`PUT /me/preferences` (operationId `updatePreferences`). Update notification & privacy preferences"""
        ...


class AuthenticationPort(Protocol):
    """Derived from OpenAPI operations: `loginEmail`, `loginGoogle`, `logout`, `registerEmail`, `requestOtp`, `startRecovery`, `verifyOtp`."""

    async def login_email(self, body: LoginEmailRequest) -> SessionEstablished:
        """`POST /auth/login/email` (operationId `loginEmail`). Log in with email and password"""
        ...

    async def login_google(self, body: GoogleSignInRequest) -> SessionEstablished:
        """`POST /auth/login/google` (operationId `loginGoogle`). Federated sign-in with Google"""
        ...

    async def logout(self) -> None:
        """`POST /auth/logout` (operationId `logout`). Log out (terminate the current session)"""
        ...

    async def register_email(self, body: RegisterEmailRequest) -> None:
        """`POST /auth/register/email` (operationId `registerEmail`). Register with email and password"""
        ...

    async def request_otp(self, body: OtpRequest) -> None:
        """`POST /auth/otp` (operationId `requestOtp`). Request a phone OTP"""
        ...

    async def start_recovery(self, body: RecoveryStartRequest) -> None:
        """`POST /auth/recovery` (operationId `startRecovery`). Start credential recovery"""
        ...

    async def verify_otp(self, body: OtpVerifyRequest) -> SessionEstablished:
        """`POST /auth/otp/verify` (operationId `verifyOtp`). Verify a phone OTP and establish a session"""
        ...


class AuthorizationPort(Protocol):
    """Authorization decisions are made by AuthorizationService and consulted in-process by every
    other module (default-deny, acting-profile scoped, Security Sec 4.2) -- never a REST
    endpoint, so there is no OpenAPI operation to derive a method from (Task P-05 designs this
    Protocol's methods; only `shared_kernel` types and primitives cross it -- `identity.domain`
    types never do, AIR-02). The concrete adapter (`identity.infrastructure`) hashes the raw
    `session_token` internally before resolving it; the hashing pepper never leaves identity."""

    async def authorize(
        self,
        *,
        session_token: str,
        required_permission: str,
        owner_account_id: UserId | None = None,
        owner_profile_id: BusinessProfileId | None = None,
    ) -> UserId:
        """The full four-gate check (Security Sec 4.2): authenticated, acting context resolved,
        permission held (default-deny, I-11), ownership/scope matches (I-10). Raises on denial;
        returns the resolved account id on success."""
        ...

    async def get_effective_permissions(self, *, session_token: str) -> frozenset[str]:
        """ "reflect-permissions": the acting context's flattened permission set, for callers
        that render capability-based UI rather than gate one specific operation. Raises the same
        Gate-1/2 failures as `authorize` for an invalid/expired session; never partially
        succeeds."""
        ...


class ContactPolicyPort(Protocol):
    """Phone-reveal gating policy (FR-USER-003, BRULE-13), consulted in-process by messaging
    (privacy-gated phone reveal) -- never a REST endpoint."""

    async def get_phone_reveal_mode(
        self, account_id: UserId
    ) -> Literal["ALWAYS", "ON_REQUEST", "NEVER"]:
        """Fail-closed: an unknown account id resolves to `"NEVER"`, never to a default that
        would reveal more than intended."""
        ...

    async def reveal_phone(self, account_id: UserId) -> str | None:
        """Task P-10 (messaging, FR-MSG-003): the mode-check and the actual phone-number read
        both stay inside identity (the module that owns the data and the decision to release
        it) -- returns the E.164 string only when `get_phone_reveal_mode` would return `"ALWAYS"`
        or `"ON_REQUEST"` (an explicit reveal request, which calling this method already IS) AND
        the account has a phone on file; returns `None` on every other path (unknown account,
        `"NEVER"`, no phone) -- fail-closed, the same discipline as `get_phone_reveal_mode`.
        Returns a plain `str`, never `identity.domain.value_objects.PhoneNumber`: only
        `shared_kernel` types and primitives may cross this Protocol (AIR-02)."""
        ...
