"""identity.interfaces -- the module's only importable public surface (AIR-02)."""

from __future__ import annotations

from identity.interfaces.dto import (
    Account,
    GoogleSignInRequest,
    LoginEmailRequest,
    NotificationPreferences,
    OtpRequest,
    OtpVerifyRequest,
    PasswordChangeRequest,
    PrivacySettings,
    RecoveryStartRequest,
    RegisterEmailRequest,
    Session,
    SessionEstablished,
    SwitchActingProfileBody,
    UpdateMeBody,
    UpdatePreferencesBody,
    UserAdminView,
    UserAdminViewPage,
    UserStatusChangeRequest,
)
from identity.interfaces.ports import (
    ActingIdentityQueryPort,
    AuthenticationPort,
    AuthorizationPort,
    ContactPolicyPort,
)

__all__ = [
    "Account",
    "ActingIdentityQueryPort",
    "AuthenticationPort",
    "AuthorizationPort",
    "ContactPolicyPort",
    "GoogleSignInRequest",
    "LoginEmailRequest",
    "NotificationPreferences",
    "OtpRequest",
    "OtpVerifyRequest",
    "PasswordChangeRequest",
    "PrivacySettings",
    "RecoveryStartRequest",
    "RegisterEmailRequest",
    "Session",
    "SessionEstablished",
    "SwitchActingProfileBody",
    "UpdateMeBody",
    "UpdatePreferencesBody",
    "UserAdminView",
    "UserAdminViewPage",
    "UserStatusChangeRequest",
]
