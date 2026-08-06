"""ads -- value objects (DDD Sec 5.9 BC-09). Persistence-ignorant, mirrors
`billing.domain.value_objects`'s style. `enum.StrEnum` for every closed vocabulary here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from ads.domain.exceptions import InvalidScheduleError


class CampaignStatus(StrEnum):
    """Verbatim from Physical Database Design's `ads.banner_campaign.status` CHECK vocabulary
    and DDD Sec 5.9's `CampaignStatus` VO. Fixed lifecycle: `DRAFT -> SCHEDULED -> RUNNING ->
    ENDED`, with `PAUSED` reachable from, and returning to, `SCHEDULED`/`RUNNING`. No event exists
    for the `PAUSED`/resumed transitions in the frozen catalogue (`contracts/events/ads.py` names
    only Scheduled/Started/Ended) -- ADR-0004."""

    DRAFT = "DRAFT"
    SCHEDULED = "SCHEDULED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    ENDED = "ENDED"


class CreativeStatus(StrEnum):
    """ads' own local cache of the referenced `MediaAssetRef`'s scan outcome (I-20: "quarantined
    assets are never delivered"), mirroring `catalog.domain.value_objects.ImageStatus`'s own
    projected-snapshot role for `ImageAttachment.status` exactly -- ads never owns this data,
    only caches media's own `scan_status` locally so the serve path never calls media live."""

    PENDING = "PENDING"
    CLEAN = "CLEAN"
    QUARANTINED = "QUARANTINED"


@dataclass(frozen=True)
class Schedule:
    """FR-BANNER-002: "a banner campaign to be scheduled with start/end dates and priority."
    `priority` lives here rather than as a sibling `BannerCampaign` field since DDD Sec 5.9's own
    VO list groups them together ("Schedule (start/end, priority)")."""

    start: datetime
    end: datetime
    priority: int

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise InvalidScheduleError("end must be strictly after start")
        if self.priority < 0:
            raise InvalidScheduleError("priority must be non-negative")

    def covers(self, now: datetime) -> bool:
        """I-21's "within its schedule" clause."""
        return self.start <= now < self.end


@dataclass(frozen=True)
class Targeting:
    """FR-BANNER-003: "basic banner targeting by category, geography, and language." Every
    dimension is optional; an unset dimension matches every request on that axis (untargeted =
    universal on that dimension, not "matches nothing")."""

    category_ids: tuple[UUID, ...] = field(default_factory=tuple)
    geo: str | None = None
    languages: tuple[str, ...] = field(default_factory=tuple)

    def matches(
        self,
        *,
        category_id: UUID | None,
        geo: str | None,
        language: str | None,
    ) -> bool:
        """I-21's "matching targeting" clause. Each set dimension must match the request's
        corresponding value; a request that omits a value never matches a campaign that targets
        that dimension (a targeted campaign requires the caller to say what it's targeting)."""
        if self.category_ids and (category_id is None or category_id not in self.category_ids):
            return False
        if self.geo is not None and (geo is None or geo != self.geo):
            return False
        return not (self.languages and (language is None or language not in self.languages))
