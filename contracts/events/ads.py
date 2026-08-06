"""ads (BC-09) domain events -- DDD Sec 6, the authoritative v1 event catalogue.

STATUS: frozen (Task P-01). Schema only: each class is the shared envelope
(`shared_kernel.EventEnvelope`) with `event_type` pinned to its own past-tense name. No
publishing logic, no handlers -- that is outbox/adapter work for a later task. Do not add an
event here that is not a row in DDD Sec 6 for this context; do not remove one either without an
ADR (Playbook Sec 18) amending the Domain Model.
"""

from __future__ import annotations

from typing import Literal

from shared_kernel import EventEnvelope


class BannerCampaignScheduled(EventEnvelope):
    """Emitted when: Campaign lifecycle.

    Principal consumers: Analytics, Notifications.
    """

    event_type: Literal["BannerCampaignScheduled"] = "BannerCampaignScheduled"


class BannerCampaignStarted(EventEnvelope):
    """Emitted when: Campaign lifecycle.

    Principal consumers: Analytics, Notifications.
    """

    event_type: Literal["BannerCampaignStarted"] = "BannerCampaignStarted"


class BannerCampaignEnded(EventEnvelope):
    """Emitted when: Campaign lifecycle.

    Principal consumers: Analytics, Notifications.
    """

    event_type: Literal["BannerCampaignEnded"] = "BannerCampaignEnded"


class BannerImpressionRecorded(EventEnvelope):
    """Emitted when: Serving/interaction.

    Principal consumers: Analytics.
    """

    event_type: Literal["BannerImpressionRecorded"] = "BannerImpressionRecorded"


class BannerClickRecorded(EventEnvelope):
    """Emitted when: Serving/interaction.

    Principal consumers: Analytics.
    """

    event_type: Literal["BannerClickRecorded"] = "BannerClickRecorded"
