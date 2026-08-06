"""notifications/infrastructure -- SQLAlchemy repositories, channel provider adapters, and the
idempotent cross-module event projection handlers (Task P-13). Never imported by `notifications.
interfaces`/`application`/`domain` -- only the composition root wires these concrete classes
behind the ports `application/` declares.
"""

from __future__ import annotations

from notifications.infrastructure.configuration_adapter import (
    ConfigurationNotificationTemplateAdapter,
)
from notifications.infrastructure.event_projection import (
    handle_ads_event,
    handle_billing_event,
    handle_catalog_event,
    handle_identity_event,
    handle_messaging_event,
    handle_moderation_event,
    handle_profiles_event,
)
from notifications.infrastructure.persistence import (
    SqlalchemyNotificationRepository,
    SqlalchemyOrderRecipientProjectionRepository,
)
from notifications.infrastructure.providers import (
    EskizSmsProviderAdapter,
    SmtpEmailProviderAdapter,
    WebPushProviderAdapter,
)

__all__ = [
    "ConfigurationNotificationTemplateAdapter",
    "EskizSmsProviderAdapter",
    "SmtpEmailProviderAdapter",
    "SqlalchemyNotificationRepository",
    "SqlalchemyOrderRecipientProjectionRepository",
    "WebPushProviderAdapter",
    "handle_ads_event",
    "handle_billing_event",
    "handle_catalog_event",
    "handle_identity_event",
    "handle_messaging_event",
    "handle_moderation_event",
    "handle_profiles_event",
]
