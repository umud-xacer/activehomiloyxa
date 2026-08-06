"""notifications/application -- ports (Task P-13). Abstract surface only (typing.Protocol);
`infrastructure/` implements every one of these, never the reverse (Clean Architecture rule 4).

`RecipientDirectoryPort` is notifications' OWN narrow local Protocol for reading a recipient's
contact info/channel preferences -- NOT `identity.interfaces.ports.ActingIdentityQueryPort`
imported directly. SAD Sec 8.1's own notifications row is `shared_kernel, configuration` only --
notifications may NOT statically import `identity` (`cross-module-notifications`, tools/
importlinter.cfg, forbids it, unlike catalog/billing/profiles, which may import identity's own
`interfaces/`). The CONCRETE bridge adapter implementing this Protocol against identity's (and,
for profile-/listing-addressed events, profiles'/catalog's own) real repositories is therefore
defined entirely in `composition_root.py` (the one place allowed to see every module's
internals), never inside `notifications/` itself -- mirrors `moderation.application.ports`'s own
"three narrow command ports, composition-root-only bridge" pattern exactly, just for READS
instead of commands.

`TemplateReaderPort` mirrors every other module's own `_ConfigurationReader`-shaped bridge to
`configuration.application.CategoryReadUseCases`/`ConfigurationUseCases` (via `composition_root.
_ConfigurationPortBridge`, unmodified) -- entity-type-agnostic, so no new bridge class is needed
there, only a new adapter here (`infrastructure/configuration_adapter.py`) narrowing it to
`notification-template` snapshots.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from notifications.domain import Notification
from shared_kernel import LocalizedText


@dataclass(frozen=True)
class WebPushSubscriptionSnapshot:
    """A registered browser push subscription. NOTE (P-13 "Known gaps"): no operation anywhere
    in `contracts/openapi.yaml` registers one -- only the `webPush` boolean opt-in exists on
    `NotificationPreferences`. This shape exists so `WebPushProviderPort`/the dispatch use case
    are real and fully tested against a synthetic subscription; in v1 no code path ever
    constructs a real one, since there is no endpoint to submit it (CLAUDE.md: "never hand-write
    or guess an endpoint that isn't an operationId... a missing endpoint is an architecture
    decision")."""

    endpoint: str
    p256dh: str
    auth: str


@dataclass(frozen=True)
class RecipientSnapshot:
    """notifications' own narrow read shape for "who am I notifying and how may I reach them" --
    deliberately NOT `identity.domain.UserAccount` (AIR-02: only `shared_kernel` types and
    primitives may cross this Protocol)."""

    user_id: UUID
    email: str | None
    phone: str | None
    web_push_subscription: WebPushSubscriptionSnapshot | None
    email_enabled: bool
    web_push_enabled: bool
    sms_enabled: bool


class RecipientDirectoryPort(Protocol):
    """Every method returns `None` (never raises) when no deliverable recipient can be resolved
    -- an anonymised/closed account, an unresolvable profile/listing owner, or (for
    `resolve_recipient_for_conversation`, deliberately NOT declared here -- see README "Known
    gaps") no reliable id exists at all. Fail-closed: the caller's job is to skip dispatch, never
    to guess a fallback contact."""

    async def resolve_recipient(self, user_id: UUID) -> RecipientSnapshot | None:
        """Direct lookup -- the event's own payload already names a `UserId` (e.g.
        `ownerUserId`/`recipientUserId`, or the event's own `aggregate_id`)."""
        ...

    async def resolve_recipient_for_profile(self, profile_id: UUID) -> RecipientSnapshot | None:
        """Billing/profiles events identify a `BusinessProfileId`, not a `UserId` directly --
        this resolves the profile's own `owner_user_id` (read from profiles' repository, inside
        `composition_root.py` only) before resolving that account's contact info."""
        ...

    async def resolve_recipient_for_listing(self, listing_id: UUID) -> RecipientSnapshot | None:
        """`ModerationActionTaken` on a `LISTING`-subject case identifies a `ListingId` -- this
        resolves the listing's own `owner_user_id` (read from catalog's repository, inside
        `composition_root.py` only) before resolving that account's contact info."""
        ...


@dataclass(frozen=True)
class NotificationTemplateSnapshot:
    """A single PUBLISHED `NotificationTemplate` version, narrowed to what dispatch needs."""

    template_id: UUID
    template_version_id: UUID
    event_key: str
    channel: str
    subject: LocalizedText | None
    body: LocalizedText


class TemplateReaderPort(Protocol):
    async def list_templates_for_event(
        self, event_key: str
    ) -> tuple[NotificationTemplateSnapshot, ...]:
        """Every PUBLISHED template snapshot whose `event_key` matches -- zero, one, or up to
        three (one per channel); which channels an event actually notifies over is entirely
        configuration-authored data (DEC-21), never hardcoded here."""
        ...


class EmailProviderPort(Protocol):
    async def send_email(self, *, to_email: str, subject: str | None, body: str) -> str:
        """Returns the provider's own opaque message id. Raises on failure (caught by the
        calling use case, never silently swallowed) -- fail-closed on missing credentials."""
        ...


class WebPushProviderPort(Protocol):
    async def send_push(self, *, subscription: WebPushSubscriptionSnapshot, body: str) -> str:
        """Returns the subscription's own endpoint as the opaque "message id" (web-push has no
        separate provider-issued message identifier)."""
        ...


class SmsProviderPort(Protocol):
    async def send_sms(self, *, phone: str, body: str) -> str:
        """Eskiz only (DEC-18) -- returns Eskiz's own opaque message id."""
        ...


class OrderRecipientProjectionRepository(Protocol):
    """Local, notifications-owned projection (not in the documented Physical Database Design --
    the same "locally necessary addition" precedent `catalog.subscription_projection`/`profiles.
    verification_entitlement_projection` already established): `InvoiceIssued`'s own payload
    carries no profile/user reference at all, so this records the `orderId -> purchaserProfileId`
    mapping `OrderPlaced`'s own consumer already resolved, for `InvoiceIssued`'s consumer to read
    moments later."""

    async def upsert(self, *, order_id: UUID, purchaser_profile_id: UUID) -> None: ...

    async def get_purchaser_profile_id(self, order_id: UUID) -> UUID | None: ...


class NotificationRepository(Protocol):
    async def add(self, notification: Notification) -> None: ...

    async def save(self, notification: Notification) -> Notification: ...

    async def get_by_id(self, notification_id: UUID) -> Notification | None: ...

    async def list_for_recipient(
        self,
        recipient_user_id: UUID,
        *,
        unread_only: bool,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[Notification], str | None]: ...
