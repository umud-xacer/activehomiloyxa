"""FastAPI routers implementing the fifteen Authentication + Users -tagged OpenAPI operations
(`contracts/openapi.yaml`, P-05 prompt scope) plus, as of Task P-16, the four
`Administration`-tagged operations on identity's own resource (`adminListUsers`/
`adminChangeUserStatus`/`assignRole`/`revokeRole`, the latter two new in ADR-0006). Thin
translation only: cookie/body -> use-case call -> domain object -> already-frozen
`interfaces/dto.py` DTO. All business logic lives in `application`/`domain`; this module owns
none.

The four `Administration`-tagged operations live HERE, not in `admin`'s own router, mirroring
exactly where `moderation`'s/`profiles`'s/`billing`'s/`analytics`'s own `Administration`-tagged
operations already live -- `contracts/README.md`'s own P-01 tag-routing rule routes an
`Administration`-tagged operation to the module owning the underlying aggregate; `RoleAssignment`
is an entity inside identity's own `UserAccount` (DDD Sec 5.1). `identity/application/
admin_use_cases.py::AdminIdentityUseCases` (built in Task P-05, previously unmounted -- both its
own README and `configuration.domain.whitelist.PERMISSION_KEYS`'s P-05 comment on
`identity:role:assign` explicitly earmarked this for "a future admin-module task") backs all
four.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Form, Header, Request, Response
from fastapi.responses import RedirectResponse

from backbone.net import resolve_client_ip
from backbone.persistence.env import required_env
from identity.application import AccountUseCases, AdminIdentityUseCases, AuthenticationUseCases
from identity.domain import (
    AccountKind,
    EmailAddress,
    OtpPurpose,
    PhoneNumber,
    PhoneRevealMode,
    UserAccount,
)
from identity.domain import NotificationPreferences as DomainNotificationPreferences
from identity.domain import PrivacySettings as DomainPrivacySettings
from identity.domain import RegistrationReviewStatus as DomainRegistrationReviewStatus
from identity.domain import Session as DomainSession
from identity.interfaces.auth import SESSION_COOKIE_NAME, ActingOperator, AuthenticatedRequest
from identity.interfaces.di import (
    get_account_use_cases,
    get_admin_identity_use_cases,
    get_authenticated_request,
    get_authentication_use_cases,
    get_registration_reviewer,
    get_roles_acting_operator,
    get_users_acting_operator,
)
from identity.interfaces.dto import (
    Account,
    AppleSignInRequest,
    GoogleSignInRequest,
    LoginEmailRequest,
    NotificationPreferences,
    OtpRequest,
    OtpVerifyRequest,
    PageInfo,
    PasswordChangeRequest,
    PhoneLinkRequest,
    PhoneLinkVerifyRequest,
    PrivacySettings,
    RecoveryStartRequest,
    RegisterEmailRequest,
    RegistrationDecisionRequest,
    RegistrationQueueItem,
    RegistrationQueuePage,
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

_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 365
"""Upper bound only -- the cookie's real lifetime is the session's own `expiresAt`; browsers
clamp `max_age` but the session is independently invalidated server-side at that time regardless
(Security Sec 3.2)."""


admin_users_router = APIRouter(tags=["Administration"])


def _account_to_admin_view(account: UserAccount) -> UserAdminView:
    return UserAdminView(
        id=account.id.value,
        phone_number=account.phone.value if account.phone else None,
        email=account.email.value if account.email else None,
        status=account.status.value,
        created_at=account.created_at,
    )


def _account_to_dto(account: UserAccount) -> Account:
    return Account(
        id=account.id.value,
        phone_number=account.phone.value if account.phone else None,
        email=account.email.value if account.email else None,
        display_name=account.display_name,
        status=account.status.value,
        privacy_settings=PrivacySettings(
            phone_reveal_mode=account.privacy_settings.phone_reveal_mode.value
        ),
        notification_preferences=NotificationPreferences(
            email=account.notification_preferences.email,
            web_push=account.notification_preferences.web_push,
            sms=account.notification_preferences.sms,
        ),
        owned_profile_ids=[p.value for p in account.owned_profile_ids] or None,
        roles=[ra.role_code for ra in account.role_assignments] or None,
        created_at=account.created_at,
        account_kind=account.account_kind.value,
        review_status=account.review_status.value,
        review_reason=account.review_decision.reason if account.review_decision else None,
    )


def _session_to_dto(session: DomainSession, *, current_session_id: UUID) -> Session:
    return Session(
        id=session.id,
        acting_profile_id=session.acting_profile_id.value if session.acting_profile_id else None,
        ip_address=session.ip_address,
        user_agent=session.user_agent,
        current=session.id == current_session_id,
        created_at=session.created_at,
        expires_at=session.expires_at,
    )


def _set_session_cookie(response: Response, raw_token: str, session: DomainSession) -> None:
    max_age = min(
        int((session.expires_at - datetime.now(UTC)).total_seconds()), _COOKIE_MAX_AGE_SECONDS
    )
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw_token,
        max_age=max(max_age, 0),
        secure=True,
        httponly=True,
        samesite="lax",
    )


def _client_ip(request: Request) -> str:
    """Thin wrapper -- the real IP-resolution logic (Cloudflare/nginx header precedence, and why)
    now lives in `backbone.net.resolve_client_ip`, shared with `configuration`'s owner-admin-access
    oracle lockout and the global rate-limit middleware. See that function's own docstring for the
    full reasoning (still applies here unchanged)."""
    return resolve_client_ip(
        request.headers, fallback_host=request.client.host if request.client else None
    )


# -- Authentication (unauthenticated) -----------------------------------------------------------

auth_router = APIRouter(tags=["Authentication"])


@auth_router.post("/auth/otp", operation_id="requestOtp", status_code=202)
async def request_otp(
    body: OtpRequest,
    request: Request,
    use_cases: AuthenticationUseCases = Depends(get_authentication_use_cases),
) -> None:
    await use_cases.request_otp(
        phone=PhoneNumber(body.phone_number),
        purpose=OtpPurpose(body.purpose),
        ip_address=_client_ip(request),
        now=datetime.now(UTC),
    )


@auth_router.post("/auth/otp/verify", operation_id="verifyOtp")
async def verify_otp(
    body: OtpVerifyRequest,
    request: Request,
    response: Response,
    use_cases: AuthenticationUseCases = Depends(get_authentication_use_cases),
) -> SessionEstablished:
    account, session, raw_token = await use_cases.verify_otp(
        phone=PhoneNumber(body.phone_number),
        code=body.code,
        purpose=OtpPurpose(body.purpose),
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        now=datetime.now(UTC),
        account_kind=AccountKind(body.account_kind),
        anketa=body.anketa,
    )
    _set_session_cookie(response, raw_token, session)
    return SessionEstablished(
        account=_account_to_dto(account),
        session=_session_to_dto(session, current_session_id=session.id),
        session_token=raw_token,
    )


@auth_router.post("/auth/register/email", operation_id="registerEmail", status_code=202)
async def register_email(
    body: RegisterEmailRequest,
    use_cases: AuthenticationUseCases = Depends(get_authentication_use_cases),
) -> None:
    await use_cases.register_email(
        email=EmailAddress(body.email),
        password=body.password,
        display_name=body.display_name,
        now=datetime.now(UTC),
        account_kind=AccountKind(body.account_kind),
        anketa=body.anketa,
    )


@auth_router.post("/auth/login/email", operation_id="loginEmail")
async def login_email(
    body: LoginEmailRequest,
    request: Request,
    response: Response,
    use_cases: AuthenticationUseCases = Depends(get_authentication_use_cases),
) -> SessionEstablished:
    account, session, raw_token = await use_cases.login_email(
        email=EmailAddress(body.email),
        password=body.password,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        now=datetime.now(UTC),
    )
    _set_session_cookie(response, raw_token, session)
    return SessionEstablished(
        account=_account_to_dto(account),
        session=_session_to_dto(session, current_session_id=session.id),
        session_token=raw_token,
    )


@auth_router.post("/auth/login/google", operation_id="loginGoogle")
async def login_google(
    body: GoogleSignInRequest,
    request: Request,
    response: Response,
    use_cases: AuthenticationUseCases = Depends(get_authentication_use_cases),
) -> SessionEstablished:
    account, session, raw_token = await use_cases.login_google(
        authorization_code=body.authorization_code,
        redirect_uri=body.redirect_uri,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        now=datetime.now(UTC),
    )
    _set_session_cookie(response, raw_token, session)
    return SessionEstablished(
        account=_account_to_dto(account),
        session=_session_to_dto(session, current_session_id=session.id),
        session_token=raw_token,
    )


@auth_router.post("/auth/login/apple", operation_id="loginApple")
async def login_apple(
    body: AppleSignInRequest,
    request: Request,
    response: Response,
    use_cases: AuthenticationUseCases = Depends(get_authentication_use_cases),
) -> SessionEstablished:
    account, session, raw_token = await use_cases.login_apple(
        authorization_code=body.authorization_code,
        redirect_uri=body.redirect_uri,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        now=datetime.now(UTC),
    )
    _set_session_cookie(response, raw_token, session)
    return SessionEstablished(
        account=_account_to_dto(account),
        session=_session_to_dto(session, current_session_id=session.id),
        session_token=raw_token,
    )


@auth_router.post("/auth/callback/apple", include_in_schema=False)
async def apple_form_post_relay(
    code: str = Form(...), state: str | None = Form(default=None)
) -> RedirectResponse:
    """Not a contracts/openapi.yaml operation (`include_in_schema=False`, excluded from QG-06 the
    same way `/health`/`/ready` already are) -- Apple's own OAuth wire protocol, not this app's
    JSON API. Sign in with Apple mandates `response_mode=form_post` whenever any scope (email,
    here) is requested: Apple POSTs `code`/`state`/etc as form fields straight to this
    `redirect_uri`, which a SPA route cannot receive directly (no server to catch the POST). This
    relay's only job is picking `code` back out and 302-ing to the real frontend callback route as
    an ordinary query string GET, which `/auth/callback/apple` (frontend) can consume like any
    other client-side OAuth redirect -- `loginApple` itself still does the real token exchange."""
    site_url = required_env("PUBLIC_SITE_URL").rstrip("/")
    query = f"code={code}" + (f"&state={state}" if state else "")
    return RedirectResponse(url=f"{site_url}/auth/callback/apple?{query}", status_code=302)


@auth_router.post("/auth/logout", operation_id="logout", status_code=204)
async def logout(
    response: Response,
    ah_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    authorization: str | None = Header(default=None),
    use_cases: AuthenticationUseCases = Depends(get_authentication_use_cases),
) -> None:
    raw_token = _raw_token(ah_session, authorization)
    if raw_token is not None:
        await use_cases.logout(raw_token=raw_token, now=datetime.now(UTC))
    response.delete_cookie(SESSION_COOKIE_NAME)


@auth_router.post("/auth/recovery", operation_id="startRecovery", status_code=202)
async def start_recovery(
    body: RecoveryStartRequest,
    request: Request,
    use_cases: AuthenticationUseCases = Depends(get_authentication_use_cases),
) -> None:
    await use_cases.start_recovery(
        phone=PhoneNumber(body.phone_number) if body.phone_number else None,
        email=EmailAddress(body.email) if body.email else None,
        ip_address=_client_ip(request),
        now=datetime.now(UTC),
    )


def _raw_token(cookie_value: str | None, authorization_header: str | None) -> str | None:
    if cookie_value:
        return cookie_value
    if authorization_header and authorization_header.lower().startswith("bearer "):
        return authorization_header[len("bearer ") :].strip()
    return None


# -- Users (session-authenticated) ---------------------------------------------------------------

users_router = APIRouter(tags=["Users"])


@users_router.get("/me", operation_id="getMe")
async def get_me(
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
) -> Account:
    return _account_to_dto(authenticated.account)


@users_router.patch("/me", operation_id="updateMe")
async def update_me(
    body: UpdateMeBody,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    use_cases: AccountUseCases = Depends(get_account_use_cases),
) -> Account:
    updated = await use_cases.update_me(
        authenticated.account.id,
        display_name=body.display_name,
        email=EmailAddress(body.email) if body.email else None,
        now=datetime.now(UTC),
    )
    return _account_to_dto(updated)


@users_router.put("/me/password", operation_id="changePassword", status_code=204)
async def change_password(
    body: PasswordChangeRequest,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    use_cases: AccountUseCases = Depends(get_account_use_cases),
) -> None:
    await use_cases.change_password(
        authenticated.account.id,
        current_password=body.current_password,
        new_password=body.new_password,
        now=datetime.now(UTC),
    )


@users_router.post("/me/phone/otp", operation_id="requestPhoneLinkOtp", status_code=202)
async def request_phone_link_otp(
    body: PhoneLinkRequest,
    request: Request,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    use_cases: AuthenticationUseCases = Depends(get_authentication_use_cases),
) -> None:
    await use_cases.request_otp(
        phone=PhoneNumber(body.phone_number),
        purpose=OtpPurpose.LINK_PHONE,
        ip_address=_client_ip(request),
        now=datetime.now(UTC),
    )


@users_router.post("/me/phone/otp/verify", operation_id="confirmPhoneLink")
async def confirm_phone_link_otp(
    body: PhoneLinkVerifyRequest,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    use_cases: AuthenticationUseCases = Depends(get_authentication_use_cases),
) -> Account:
    account = await use_cases.confirm_phone_link(
        account_id=authenticated.account.id,
        phone=PhoneNumber(body.phone_number),
        code=body.code,
        now=datetime.now(UTC),
    )
    return _account_to_dto(account)


@users_router.put("/me/preferences", operation_id="updatePreferences")
async def update_preferences(
    body: UpdatePreferencesBody,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    use_cases: AccountUseCases = Depends(get_account_use_cases),
) -> Account:
    privacy = (
        DomainPrivacySettings(
            phone_reveal_mode=PhoneRevealMode(body.privacy_settings.phone_reveal_mode)
        )
        if body.privacy_settings is not None and body.privacy_settings.phone_reveal_mode is not None
        else None
    )
    notifications = (
        DomainNotificationPreferences(
            email=body.notification_preferences.email
            if body.notification_preferences.email is not None
            else True,
            web_push=body.notification_preferences.web_push
            if body.notification_preferences.web_push is not None
            else False,
            sms=body.notification_preferences.sms
            if body.notification_preferences.sms is not None
            else True,
        )
        if body.notification_preferences is not None
        else None
    )
    updated = await use_cases.update_preferences(
        authenticated.account.id,
        privacy_settings=privacy,
        notification_preferences=notifications,
        now=datetime.now(UTC),
    )
    return _account_to_dto(updated)


@users_router.delete("/me/account", operation_id="closeAccount", status_code=204)
async def close_account(
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    use_cases: AccountUseCases = Depends(get_account_use_cases),
) -> None:
    await use_cases.close_account(authenticated.account.id, now=datetime.now(UTC))


@users_router.get("/me/sessions", operation_id="listSessions")
async def list_sessions(
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    use_cases: AccountUseCases = Depends(get_account_use_cases),
) -> list[Session]:
    sessions = await use_cases.list_sessions(authenticated.account.id)
    return [_session_to_dto(s, current_session_id=authenticated.session.id) for s in sessions]


@users_router.delete("/me/sessions/{sessionId}", operation_id="revokeSession", status_code=204)
async def revoke_session(
    sessionId: UUID,  # must match the {sessionId} path template exactly (contracts/openapi.yaml)
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    use_cases: AccountUseCases = Depends(get_account_use_cases),
) -> None:
    await use_cases.revoke_session(authenticated.account.id, sessionId)


@users_router.post("/me/sessions/switch-profile", operation_id="switchActingProfile")
async def switch_acting_profile(
    body: SwitchActingProfileBody,
    authenticated: AuthenticatedRequest = Depends(get_authenticated_request),
    use_cases: AccountUseCases = Depends(get_account_use_cases),
) -> Session:
    new_profile_id = (
        BusinessProfileId(value=body.acting_profile_id)
        if body.acting_profile_id is not None
        else None
    )
    updated = await use_cases.switch_acting_profile(
        authenticated.account.id,
        authenticated.session.id,
        new_acting_profile_id=new_profile_id,
        now=datetime.now(UTC),
    )
    return _session_to_dto(updated, current_session_id=authenticated.session.id)


def _clamp_limit(limit: int | None) -> int:
    return min(max(limit or 20, 1), 100)


@admin_users_router.get("/admin/users", operation_id="adminListUsers")
async def admin_list_users(
    status: str | None = None,
    query: str | None = None,
    cursor: str | None = None,
    limit: int | None = 20,
    _operator: ActingOperator = Depends(get_users_acting_operator),
    use_cases: AdminIdentityUseCases = Depends(get_admin_identity_use_cases),
) -> UserAdminViewPage:
    """FR-ADMIN-001. Gated by `identity:account:manage_status`."""
    accounts, next_cursor = await use_cases.list_users(
        status=status, query=query, cursor=cursor, limit=_clamp_limit(limit)
    )
    total = await use_cases.count_users()
    return UserAdminViewPage(
        items=[_account_to_admin_view(a) for a in accounts],
        page=PageInfo(limit=_clamp_limit(limit), next_cursor=next_cursor, total=total),
    )


@admin_users_router.post("/admin/users/{userId}/status", operation_id="adminChangeUserStatus")
async def admin_change_user_status(
    userId: UUID,
    body: UserStatusChangeRequest,
    _operator: ActingOperator = Depends(get_users_acting_operator),
    use_cases: AdminIdentityUseCases = Depends(get_admin_identity_use_cases),
) -> UserAdminView:
    """FR-ADMIN-001. Suspends or reactivates an account (emits `AccountSuspended`; catalog hides
    listings via events). Audited (I-22, via identity's own outbox -> analytics)."""
    updated = await use_cases.change_user_status(
        target_account_id=UserId(value=userId),
        action=body.action,
        reason=body.reason,
        now=datetime.now(UTC),
    )
    return _account_to_admin_view(updated)


@admin_users_router.post("/admin/users/{userId}/roles", operation_id="assignRole")
async def assign_role(
    userId: UUID,
    body: RoleAssignmentRequest,
    operator: ActingOperator = Depends(get_roles_acting_operator),
    use_cases: AdminIdentityUseCases = Depends(get_admin_identity_use_cases),
) -> UserAdminView:
    """FR-ADMIN-006 (assignment half, ADR-0006). Gated by `identity:role:assign`. Pins the
    identity + the exact published RoleDefinition version at assignment time (Config Framework
    Sec 7.2) -- permission semantics themselves are never redefined here, only composed from the
    already-published, whitelisted set."""
    acting_profile_id = (
        BusinessProfileId(value=body.acting_profile_id)
        if body.acting_profile_id is not None
        else None
    )
    updated = await use_cases.assign_role(
        actor_id=operator.account_id,
        target_account_id=UserId(value=userId),
        role_code=body.role_code,
        acting_profile_id=acting_profile_id,
        now=datetime.now(UTC),
    )
    return _account_to_admin_view(updated)


@admin_users_router.delete(
    "/admin/users/{userId}/roles/{roleDefinitionHeadId}", operation_id="revokeRole"
)
async def revoke_role(
    userId: UUID,
    roleDefinitionHeadId: UUID,
    actingProfileId: UUID | None = None,
    _operator: ActingOperator = Depends(get_roles_acting_operator),
    use_cases: AdminIdentityUseCases = Depends(get_admin_identity_use_cases),
) -> UserAdminView:
    """FR-ADMIN-006 (revocation half, ADR-0006). Gated by `identity:role:assign`."""
    acting_profile_id = (
        BusinessProfileId(value=actingProfileId) if actingProfileId is not None else None
    )
    updated = await use_cases.revoke_role(
        target_account_id=UserId(value=userId),
        role_definition_head_id=roleDefinitionHeadId,
        acting_profile_id=acting_profile_id,
        now=datetime.now(UTC),
    )
    return _account_to_admin_view(updated)


# -- Registration review (ADR-0007) --------------------------------------------------------------


def _account_to_queue_item(account: UserAccount) -> RegistrationQueueItem:
    return RegistrationQueueItem(
        id=account.id.value,
        phone_number=account.phone.value if account.phone else None,
        email=account.email.value if account.email else None,
        display_name=account.display_name,
        account_kind=account.account_kind.value,
        anketa=account.anketa,
        created_at=account.created_at,
    )


@admin_users_router.get("/admin/registration-queue", operation_id="listRegistrationQueue")
async def list_registration_queue(
    cursor: str | None = None,
    limit: int | None = 20,
    _operator: ActingOperator = Depends(get_registration_reviewer),
    use_cases: AdminIdentityUseCases = Depends(get_admin_identity_use_cases),
) -> RegistrationQueuePage:
    """ADR-0007. Gated by `identity:registration:review`."""
    accounts, next_cursor = await use_cases.list_registration_queue(
        cursor=cursor, limit=_clamp_limit(limit)
    )
    return RegistrationQueuePage(
        items=[_account_to_queue_item(a) for a in accounts],
        page=PageInfo(limit=_clamp_limit(limit), next_cursor=next_cursor),
    )


@admin_users_router.post(
    "/admin/registration-queue/{accountId}/decision", operation_id="decideRegistration"
)
async def decide_registration(
    accountId: UUID,
    body: RegistrationDecisionRequest,
    operator: ActingOperator = Depends(get_registration_reviewer),
    use_cases: AdminIdentityUseCases = Depends(get_admin_identity_use_cases),
) -> UserAdminView:
    """ADR-0007. Gated by `identity:registration:review`."""
    updated = await use_cases.decide_registration(
        target_account_id=UserId(value=accountId),
        reviewer_user_id=operator.account_id,
        outcome=DomainRegistrationReviewStatus(body.outcome),
        reason=body.reason,
        now=datetime.now(UTC),
    )
    return _account_to_admin_view(updated)
