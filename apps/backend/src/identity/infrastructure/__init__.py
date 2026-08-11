"""identity/infrastructure -- SQLAlchemy repositories, Redis session store, Eskiz/Google/SMTP
provider adapters, and the configuration-reading adapter (Task P-05). Never imported by
`identity.interfaces`/`application`/`domain` (`no-infra-inbound-identity`,
tools/importlinter.cfg) -- only the composition root (outside every module's package tree) wires
these concrete classes behind the ports `application/`/`interfaces/` declare."""

from __future__ import annotations

from identity.infrastructure.configuration_adapter import (
    ConfigurationPlatformSettingsAdapter,
    ConfigurationRoleDefinitionAdapter,
)
from identity.infrastructure.event_projection import handle_profiles_event
from identity.infrastructure.login_attempt_tracker import RedisLoginAttemptTracker
from identity.infrastructure.persistence import (
    SqlalchemyOtpChallengeRepository,
    SqlalchemyOtpChallengeUnitOfWork,
    SqlalchemyUserAccountRepository,
)
from identity.infrastructure.providers.apple_oauth import AppleOAuthProviderAdapter
from identity.infrastructure.providers.email import SmtpEmailProviderAdapter
from identity.infrastructure.providers.eskiz import EskizSmsProviderAdapter
from identity.infrastructure.providers.google_oauth import GoogleOAuthProviderAdapter
from identity.infrastructure.public_port_adapters import (
    AuthorizationPortAdapter,
    ContactPolicyPortAdapter,
)
from identity.infrastructure.security import (
    Argon2PasswordHasherAdapter,
    OtpCodeGeneratorAdapter,
    SessionTokenGeneratorAdapter,
)
from identity.infrastructure.session_store import RedisSessionRepository

__all__ = [
    "AppleOAuthProviderAdapter",
    "Argon2PasswordHasherAdapter",
    "AuthorizationPortAdapter",
    "ConfigurationPlatformSettingsAdapter",
    "ConfigurationRoleDefinitionAdapter",
    "ContactPolicyPortAdapter",
    "EskizSmsProviderAdapter",
    "GoogleOAuthProviderAdapter",
    "OtpCodeGeneratorAdapter",
    "RedisLoginAttemptTracker",
    "RedisSessionRepository",
    "SessionTokenGeneratorAdapter",
    "SmtpEmailProviderAdapter",
    "SqlalchemyOtpChallengeRepository",
    "SqlalchemyOtpChallengeUnitOfWork",
    "SqlalchemyUserAccountRepository",
    "handle_profiles_event",
]
