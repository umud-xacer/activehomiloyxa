"""ads -- DTOs (Task P-14). Translated field-for-field from the `Ads`-tagged OpenAPI operations
(`contracts/openapi.yaml`, ADR-0004). Schema only: no aggregate type is exposed here, no business
behaviour, no validation beyond what Pydantic itself does structurally.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from active_home_shared import CamelModel


class PageInfo(CamelModel):
    """Cursor pagination metadata (OpenAPI `CursorPage.page`)."""

    limit: int
    next_cursor: str | None = None
    total: int | None = None


class Targeting(CamelModel):
    """FR-BANNER-003 basic targeting -- category/geo/language, all optional (OpenAPI
    `BannerCampaign.targeting` / `BannerCampaignCreateRequest.targeting`)."""

    category_ids: list[UUID] = Field(default_factory=list)
    geo: str | None = None
    languages: list[Literal["uz_latn", "uz_cyrl", "ru", "en"]] = Field(default_factory=list)


class BannerCampaign(CamelModel):
    """A scheduled, targeted banner engagement (DDD Sec 5.9). Carries no impression/click
    counters (Database Architecture's counters-correction note; I-23)."""

    id: UUID
    slot_key: str
    creative_media_asset_id: UUID
    entitlement_id: UUID
    schedule_start: datetime
    schedule_end: datetime
    priority: int
    targeting: Targeting
    status: Literal["DRAFT", "SCHEDULED", "RUNNING", "PAUSED", "ENDED"]
    created_at: datetime | None = None
    updated_at: datetime | None = None
    target_url: str | None = None
    """Additive: optional click-through destination. `None` renders the creative as a plain,
    non-anchor image."""


class BannerCampaignPage(CamelModel):
    """A cursor-paginated page of `BannerCampaign` (OpenAPI `CursorPage` composed with
    `items: BannerCampaign[]` via `allOf`)."""

    items: list[BannerCampaign]
    page: PageInfo


class BannerCampaignCreateRequest(CamelModel):
    slot_key: str
    creative_media_asset_id: UUID
    schedule_start: datetime
    schedule_end: datetime
    priority: int
    targeting: Targeting = Targeting()
    target_url: str | None = None
    """Additive: optional click-through destination."""
    entitlement_id: UUID | None = None
    """Additive relaxation: was required, now optional. `None` triggers the owner-direct-placement
    entitlement auto-provisioning in `CampaignUseCases.create_campaign` -- see its own docstring."""


class BannerCampaignUpdateRequest(CamelModel):
    """Every field optional -- only supplied fields are mutated (OpenAPI's own description)."""

    creative_media_asset_id: UUID | None = None
    schedule_start: datetime | None = None
    schedule_end: datetime | None = None
    priority: int | None = None
    targeting: Targeting | None = None
    target_url: str | None = None
    """Additive: optional click-through destination."""


class BannerServeView(CamelModel):
    """The single eligible banner selected for a slot/context (FR-BANNER-004). Deliberately
    minimal -- no operator-only fields."""

    campaign_id: UUID
    slot_key: str
    creative_media_asset_id: UUID
    target_url: str | None = None
    """Additive: optional click-through destination for the served creative."""


class BannerServeManyResult(CamelModel):
    """Carousel/native-variant sibling of `BannerServeView` -- every eligible campaign for a
    slot/context, up to the requested limit, in the same priority order `serveBanner` itself
    picks its single winner from."""

    items: list[BannerServeView]
