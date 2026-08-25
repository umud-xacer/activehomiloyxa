"""profiles/application -- ports (Task P-11). Abstract surface only (typing.Protocol);
`infrastructure/` implements every one of these, never the reverse (Clean Architecture rule 4).

Every cross-module read is shaped as profiles' *own* narrow Protocol/dataclass here -- never a
`media.interfaces.dto`/`identity.interfaces.dto` type imported directly into this file -- the
same discipline `catalog.application.ports`'s own docstring documents (`MediaAssetReaderPort`
below mirrors `catalog.application.ports.MediaAssetReaderPort` almost exactly). The concrete
adapter bridging to the other module's `interfaces/` package lives in `profiles/infrastructure/`,
wired only at the composition root (`cross-module-profiles`, tools/importlinter.cfg).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from profiles.domain import (
    BusinessProfile,
    CaseStatus,
    MainCategory,
    ProfileType,
    SubCategory,
    VerificationCase,
)
from shared_kernel import BusinessProfileId, UserId


class BusinessProfileRepository(Protocol):
    """One repository per aggregate (`BusinessProfile`, including its `PortfolioItem` child
    entities -- Clean Architecture rule 2)."""

    async def get_by_id(self, profile_id: BusinessProfileId) -> BusinessProfile | None: ...

    async def add(self, profile: BusinessProfile) -> None: ...

    async def save(self, profile: BusinessProfile) -> BusinessProfile:
        """Returns the persisted aggregate with its post-flush `lock_version`
        (`backbone.persistence.AggregateMixin`) -- callers must use the returned value, mirroring
        `catalog.application.ports.ListingRepository.save`'s own documented contract. May raise
        `profiles.application.exceptions.StaleProfileVersionError`."""
        ...

    async def list_by_owner(
        self, owner_user_id: UserId, *, cursor: str | None, limit: int
    ) -> tuple[list[BusinessProfile], str | None]: ...

    async def list_public(
        self,
        *,
        profile_type: ProfileType | None,
        main_category: MainCategory | None,
        sub_category: SubCategory | None,
        verified_only: bool,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[BusinessProfile], str | None]:
        """Backs `listBusinessProfiles`. Only `ACTIVE` profiles are publicly listable (ADR-0012:
        `CREATED`/`PENDING_REVIEW`/`REJECTED` are all pre-approval, `ARCHIVED` is closed);
        `verified_only` filters to `badge.status == VALID`. `main_category` (additive,
        Organizations Main-Category task) filters to that sector tab -- a profile with `None`
        main_category never matches any non-null filter value, same as any other None-vs-value
        equality filter. `sub_category` (additive, Organizations Sub-Category task) is the same
        kind of filter one level finer -- callers are expected to only pass a `sub_category` that
        actually belongs to the `main_category` they also passed (the directory UI's dependent
        dropdown enforces this; this port does not re-validate it)."""
        ...

    async def list_admin(
        self, *, status: str | None, cursor: str | None, limit: int
    ) -> tuple[list[BusinessProfile], str | None]:
        """Backs `adminListBusinessProfiles` (owner-admin panel) -- unlike `list_public`, includes
        `ARCHIVED` profiles and accepts an explicit `status` filter instead of always excluding
        one; ordered oldest-first, same cursor shape as `list_public`."""
        ...

    async def count_all(self) -> int:
        """Backs the owner-admin panel's "total companies" stat -- a plain `COUNT(*)` over every
        `BusinessProfile` regardless of status, mirroring `identity.application.ports.
        UserAccountRepository.count_all`."""
        ...

    async def get_by_portfolio_media_asset_id(self, media_asset_id: UUID) -> BusinessProfile | None:
        """Backs the media asset-status projection (X-06): at most one profile holds a given
        media asset attached as a portfolio item at a time."""
        ...

    async def list_badges_expiring(self, *, now: datetime, limit: int) -> list[BusinessProfile]:
        """Backs the badge-expiry sweep worker (FR-PROF-006/007): `badge.status == VALID` and
        `badge.valid_until <= now`."""
        ...

    async def get_by_slug(self, slug: str) -> BusinessProfile | None:
        """ADR-0010: backs the public `getBusinessProfileBySlug` landing-page read. `slug` is
        display-only routing, not a unique identity by design (see `_generate_slug`'s own
        docstring) -- in the practically-impossible event of a collision, returns the most
        recently created match, same "newest wins" tiebreak `get_by_portfolio_media_asset_id`'s
        sibling reads use nowhere else needing one today."""
        ...

    async def list_trials_expiring(self, *, now: datetime, limit: int) -> list[BusinessProfile]:
        """ADR-0010: backs `TrialExpiryWorker`. Every profile with `trial_ends_at <= now` whose
        `subscription_entitlement_projection` row is STILL the trial grant itself (not since
        superseded by a paid purchase) -- the repository, not the use case, is responsible for
        this join since `BusinessProfileRepository` and `SubscriptionEligibilityRepository` are
        both profiles-module-local tables, no cross-module read involved."""
        ...


class VerificationCaseRepository(Protocol):
    """A distinct repository for the distinct `VerificationCase` aggregate root."""

    async def get_by_id(self, case_id: UUID) -> VerificationCase | None: ...

    async def get_current_for_profile(
        self, profile_id: BusinessProfileId
    ) -> VerificationCase | None:
        """Backs `getVerificationCase`: "the current verification case" -- the most recently
        created case for this profile (`REQUESTED`/`IN_REVIEW` if one is in flight, else the most
        recent terminal one, so a profile owner can see the outcome of a past decision)."""
        ...

    async def add(self, case: VerificationCase) -> None: ...

    async def save(self, case: VerificationCase) -> VerificationCase:
        """May raise `profiles.application.exceptions.StaleVerificationCaseVersionError`."""
        ...

    async def list_queue(
        self, *, status: CaseStatus | None, cursor: str | None, limit: int
    ) -> tuple[list[VerificationCase], str | None]:
        """Backs `listVerificationQueue`, reviewer-only (Security-restricted at the router/
        composition-root layer via `profiles:verification:review`, not here)."""
        ...

    async def get_by_document_media_asset_id(self, media_asset_id: UUID) -> VerificationCase | None:
        """Backs the media asset-status projection (X-06)."""
        ...


@dataclass(frozen=True)
class VerificationEligibilitySnapshot:
    """A locally projected read model of a billing `VerificationEligibility` entitlement (I-12:
    "profiles must NOT import billing" -- this row is written only by
    `EntitlementProjectionUseCases.apply_entitlement_projection`'s idempotent consumer of
    billing's *outbox events*, never by a synchronous call into billing, which profiles has no
    static dependency on at all, SAD Sec 8.1). Physical DB `profiles.
    verification_entitlement_projection` (not in the documented Physical Database Design --
    a locally-necessary projection table this task adds, the same precedent `catalog.
    subscription_projection` set for I-08 under Task P-07): keyed by `entitlement_id` (not by
    profile) so `decide_verification` can still resolve THIS case's own entitlement's
    `valid_until` at approval time even if a newer entitlement has since superseded it for the
    profile (DDD Sec 5.2 `BadgeIssuanceService`: "computes validity period from the configured
    verification product terms" -- transitively, via the entitlement's own validity window)."""

    entitlement_id: UUID
    business_profile_id: BusinessProfileId
    valid_from: datetime
    valid_until: datetime
    activation_state: Literal["ACTIVE", "EXPIRED", "REVOKED"]
    source_event_id: UUID
    """The billing event id this snapshot was last written from -- the idempotency key
    `apply_entitlement_projection` upserts on."""


class VerificationEligibilityRepository(Protocol):
    async def get_active_for_profile(
        self, profile_id: BusinessProfileId, *, now: datetime
    ) -> VerificationEligibilitySnapshot | None:
        """I-12's own eligibility check: the most recent `ACTIVE` snapshot for this profile whose
        `valid_until` has not passed; `None` if no such row exists (fails closed --
        `VerificationUseCases.request_verification` treats `None` as "not eligible")."""
        ...

    async def get_by_entitlement_id(
        self, entitlement_id: UUID
    ) -> VerificationEligibilitySnapshot | None: ...

    async def upsert(self, snapshot: VerificationEligibilitySnapshot) -> None: ...


@dataclass(frozen=True)
class SubscriptionEligibilitySnapshot:
    """A locally projected read model of a billing `ACTIVE_SUBSCRIPTION` entitlement -- the
    monetization-task sibling of `VerificationEligibilitySnapshot` above, same reasoning (profiles
    must NOT import billing; written only by the idempotent outbox consumer). Physical DB
    `profiles.subscription_entitlement_projection`: keyed by `business_profile_id` (not by
    entitlement, unlike verification's own table) -- a profile has at most one CURRENT
    subscription state that `get_active_for_profile` needs to resolve, and a later entitlement
    (a renewal) always supersedes the row rather than needing the older one kept queryable."""

    business_profile_id: BusinessProfileId
    entitlement_id: UUID
    valid_from: datetime
    valid_until: datetime
    activation_state: Literal["ACTIVE", "EXPIRED", "REVOKED"]
    source_event_id: UUID
    """The billing event id this snapshot was last written from -- the idempotency key
    `apply_subscription_projection` upserts on."""


class SubscriptionEligibilityRepository(Protocol):
    async def get_for_profile(
        self, profile_id: BusinessProfileId
    ) -> SubscriptionEligibilitySnapshot | None:
        """The profile's current subscription snapshot, whatever its `activation_state` -- the
        caller (`ProfileUseCases.get_subscription_status`) decides ACTIVE-vs-lapsed against
        `valid_until`/`activation_state` itself, mirroring `get_active_for_profile`'s own
        "fails closed on `None`" reasoning one level up."""
        ...

    async def upsert(self, snapshot: SubscriptionEligibilitySnapshot) -> None: ...


@dataclass(frozen=True)
class MediaAssetSnapshot:
    """profiles' own narrow read shape for a `MediaAsset` (X-06: "Profiles ... hold
    `MediaAssetRef` only") -- not `media.interfaces.dto.MediaAsset`."""

    id: UUID
    scan_status: Literal["PENDING", "CLEAN", "QUARANTINED"]
    content_type: str | None = None
    """Additive (promo-video business rule support): lets `ProfileUseCases.add_promo_video`
    reject a non-video asset without profiles needing any wider access to `media`."""
    duration_seconds: float | None = None
    """Additive: the same field `media.interfaces.dto.MediaAsset` exposes, read-only here too --
    `None` for images/GIF, or for a video whose duration `media`'s own probe could not read."""


class MediaAssetReaderPort(Protocol):
    """The concrete adapter calls `media.interfaces.ports.MediaIntakePort.get_media` only
    (`cross-module-profiles`)."""

    async def get_media_asset(self, media_asset_id: UUID) -> MediaAssetSnapshot | None: ...
