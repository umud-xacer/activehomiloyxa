"""identity/application -- use cases + ports (Task P-05). Depends only on `identity.domain`,
`shared_kernel`, `contracts.events.identity`, and `configuration.interfaces`."""

from __future__ import annotations

from identity.application.account_use_cases import AccountUseCases
from identity.application.admin_use_cases import AdminIdentityUseCases
from identity.application.auth_use_cases import AuthenticationUseCases
from identity.application.authorization_service import ApplicationAuthorizationService
from identity.application.exceptions import (
    AccountNotFoundError,
    IdentityApplicationError,
    InvalidGoogleCredentialError,
    InvalidSessionTokenError,
    OtpChallengeNotFoundError,
    RecoveryTargetRequiredError,
    RoleDefinitionNotFoundError,
    SessionNotFoundError,
)
from identity.application.ports import (
    EmailProviderPort,
    GoogleIdentity,
    GoogleOAuthProviderPort,
    IdentityPlatformSettings,
    LoginAttemptTrackerPort,
    OtpChallengeRepository,
    OtpCodeGeneratorPort,
    OtpSmsProviderPort,
    PasswordHasherPort,
    PlatformSettingsReaderPort,
    ResolvedRoleDefinition,
    RoleDefinitionReaderPort,
    SessionRepository,
    SessionTokenGeneratorPort,
    UserAccountRepository,
)

__all__ = [
    "AccountNotFoundError",
    "AccountUseCases",
    "AdminIdentityUseCases",
    "ApplicationAuthorizationService",
    "AuthenticationUseCases",
    "EmailProviderPort",
    "GoogleIdentity",
    "GoogleOAuthProviderPort",
    "IdentityApplicationError",
    "IdentityPlatformSettings",
    "InvalidGoogleCredentialError",
    "InvalidSessionTokenError",
    "LoginAttemptTrackerPort",
    "OtpChallengeNotFoundError",
    "OtpChallengeRepository",
    "OtpCodeGeneratorPort",
    "OtpSmsProviderPort",
    "PasswordHasherPort",
    "PlatformSettingsReaderPort",
    "RecoveryTargetRequiredError",
    "ResolvedRoleDefinition",
    "RoleDefinitionNotFoundError",
    "RoleDefinitionReaderPort",
    "SessionNotFoundError",
    "SessionRepository",
    "SessionTokenGeneratorPort",
    "UserAccountRepository",
]
