"""catalog (BC-03) domain events -- DDD Sec 6, the authoritative v1 event catalogue.

STATUS: frozen (Task P-01). Schema only: each class is the shared envelope
(`shared_kernel.EventEnvelope`) with `event_type` pinned to its own past-tense name. No
publishing logic, no handlers -- that is outbox/adapter work for a later task. Do not add an
event here that is not a row in DDD Sec 6 for this context; do not remove one either without an
ADR (Playbook Sec 18) amending the Domain Model.
"""

from __future__ import annotations

from typing import Literal

from shared_kernel import EventEnvelope


class ListingCreated(EventEnvelope):
    """Emitted when: Creation.

    Principal consumers: -- (internal), Analytics.
    """

    event_type: Literal["ListingCreated"] = "ListingCreated"


class ListingDraftSaved(EventEnvelope):
    """Emitted when: Draft save.

    Principal consumers: -- (internal), Analytics.
    """

    event_type: Literal["ListingDraftSaved"] = "ListingDraftSaved"


class ListingPublished(EventEnvelope):
    """Emitted when: Publication (unflagged).

    Principal consumers: Search (index), Notifications, Analytics.
    """

    event_type: Literal["ListingPublished"] = "ListingPublished"


class ListingEdited(EventEnvelope):
    """Emitted when: Owner edit.

    Principal consumers: Search (re-index), Moderation (optional re-flag).
    """

    event_type: Literal["ListingEdited"] = "ListingEdited"


class ListingSuspended(EventEnvelope):
    """Emitted when: Lifecycle transition.

    Principal consumers: Search (index update), Notifications.
    """

    event_type: Literal["ListingSuspended"] = "ListingSuspended"


class ListingArchived(EventEnvelope):
    """Emitted when: Lifecycle transition.

    Principal consumers: Search (index update), Notifications.
    """

    event_type: Literal["ListingArchived"] = "ListingArchived"


class ListingDeleted(EventEnvelope):
    """Emitted when: Lifecycle transition.

    Principal consumers: Search (index update), Notifications.
    """

    event_type: Literal["ListingDeleted"] = "ListingDeleted"


class ListingSold(EventEnvelope):
    """Emitted when: Lifecycle transition ("Mark as Sold").

    Added 2026-08-25, a deliberate, documented extension of this catalogue for a real product
    need -- the same precedent `ListingViewed`/`ContactButtonClicked`/`PremiumListingStat` below
    already set for ADR-0005 (do not reuse `ListingArchived` for this: notifications' own
    `queue_for_event` looks up a template by `event_type` literally, so reusing another event's
    name would render that event's own message text for a "sold" transition).

    Principal consumers: Search (index update), Notifications.
    """

    event_type: Literal["ListingSold"] = "ListingSold"


class ListingExpired(EventEnvelope):
    """Emitted when: Lifecycle transition.

    Principal consumers: Search (index update), Notifications.
    """

    event_type: Literal["ListingExpired"] = "ListingExpired"


class ListingRenewed(EventEnvelope):
    """Emitted when: Lifecycle transition.

    Principal consumers: Search (index update), Notifications.
    """

    event_type: Literal["ListingRenewed"] = "ListingRenewed"


class ListingFlagged(EventEnvelope):
    """Emitted when: Automated validation or duplicate detection.

    Principal consumers: Moderation (open case).
    """

    event_type: Literal["ListingFlagged"] = "ListingFlagged"


class FavoriteAdded(EventEnvelope):
    """Emitted when: Favorite change.

    Principal consumers: Analytics.
    """

    event_type: Literal["FavoriteAdded"] = "FavoriteAdded"


class FavoriteRemoved(EventEnvelope):
    """Emitted when: Favorite change.

    Principal consumers: Analytics.
    """

    event_type: Literal["FavoriteRemoved"] = "FavoriteRemoved"


class ListingViewed(EventEnvelope):
    """Emitted when: A listing's detail view renders (FR-ADV-010). Added by ADR-0005 -- absent
    from DDD Sec 6's published table despite Sec 5.3's own `ViewRecordingPolicy` naming it by
    this exact name; no real producer wired yet (see the ADR).

    Principal consumers: Analytics.
    """

    event_type: Literal["ListingViewed"] = "ListingViewed"


class ContactButtonClicked(EventEnvelope):
    """Emitted when: A user clicks the listing detail page's "contact seller" call-to-action,
    prior to choosing a specific channel (phone reveal or chat, each already its own metric).
    Added by ADR-0005; no real producer wired yet (see the ADR).

    Principal consumers: Analytics.
    """

    event_type: Literal["ContactButtonClicked"] = "ContactButtonClicked"


class PremiumListingStat(EventEnvelope):
    """Emitted when: An engagement fact occurs on a listing currently carrying an active
    PromotionMarker (Premium/Featured/TopPlacement). Added by ADR-0005; no real producer wired
    yet (see the ADR).

    Principal consumers: Analytics.
    """

    event_type: Literal["PremiumListingStat"] = "PremiumListingStat"
