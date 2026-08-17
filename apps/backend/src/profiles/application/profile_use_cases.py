"""profiles/application -- `ProfileUseCases` (Task P-11): create/update/archive a
`BusinessProfile`, portfolio add/remove/list, query (owner/public listing), the moderation-invoked
archive/revoke-badge commands, and the media asset-status projection for portfolio items. Every
method takes the caller's own resolved `UserId` -- authentication (a valid session) is resolved by
the router via `ActingUser` before any of these run, the same self-service trust boundary
`catalog.application.listing_use_cases.ListingUseCases` documents; ownership beyond "is
authenticated" is checked here via `profiles.application.exceptions.NotProfileOwnerError`. State
transition + outbox event append happen on the same session before one commit
(`infrastructure/` owns the transaction boundary, this layer just calls both in order).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from contracts.events.profiles import (
    BusinessProfileCreated,
    TrialSubscriptionEnded,
    TrialSubscriptionStarted,
    VerifiedBadgeExpired,
)
from profiles.application.exceptions import (
    MediaAssetNotFoundError,
    NotProfileOwnerError,
    ProfileNotFoundError,
    ProfileNotPubliclyVisibleError,
    PromoVideoNotReadyError,
    PromoVideoNotVideoError,
    PromoVideoTooLongError,
)
from profiles.application.ports import (
    BusinessProfileRepository,
    MediaAssetReaderPort,
    SubscriptionEligibilityRepository,
    SubscriptionEligibilitySnapshot,
)
from profiles.domain import BusinessProfile, MainCategory, ProfileType
from shared_kernel import BusinessProfileId, LocalizedText, OutboxPort, UserId

SubscriptionStatus = Literal["ACTIVE", "EXPIRED", "NONE"]

MAX_PROMO_VIDEO_DURATION_SECONDS = 30.0
"""Landing-page promo-video business rule (site-owner spec): each attached video must be 30
seconds or shorter -- enforced here (not on the aggregate) since duration is a fact about the
referenced `media` asset, read via `MediaAssetReaderPort`."""

_PROMO_VIDEO_CONTENT_TYPES = ("video/mp4", "video/webm")


class ProfileUseCases:
    def __init__(
        self,
        *,
        profiles: BusinessProfileRepository,
        media: MediaAssetReaderPort,
        outbox: OutboxPort,
        subscriptions: SubscriptionEligibilityRepository | None = None,
    ) -> None:
        """`subscriptions` is optional so every existing construction site (moderation commands,
        the badge-expiry worker, portfolio management -- none of which touch subscription state)
        keeps working unchanged; only the request-path composition root and the entitlement
        projection consumer need to pass a real one."""
        self._profiles = profiles
        self._media = media
        self._outbox = outbox
        self._subscriptions = subscriptions

    # --- creation (FR-PROF-001) -----------------------------------------------------------------

    async def create_profile(
        self,
        *,
        owner_user_id: UserId,
        profile_type: ProfileType,
        name: LocalizedText,
        description: LocalizedText | None,
        contacts: dict[str, Any] | None,
        address: str | None,
        now: datetime,
        main_category: MainCategory | None = None,
    ) -> BusinessProfile:
        profile_id = BusinessProfileId(value=uuid4())
        slug = _generate_slug(name, profile_id.value)
        profile = BusinessProfile.create(
            profile_id=profile_id,
            owner_user_id=owner_user_id,
            profile_type=profile_type,
            name=name,
            description=description,
            contacts=contacts,
            address=address,
            slug=slug,
            now=now,
            main_category=main_category,
        )
        profile = profile.activate(now=now)
        await self._profiles.add(profile)
        await self._outbox.append(
            BusinessProfileCreated(
                event_id=uuid4(),
                occurred_at=now,
                actor=owner_user_id.value,
                aggregate_type="BusinessProfile",
                aggregate_id=profile.id.value,
                payload={
                    "businessProfileId": str(profile.id.value),
                    "ownerUserId": str(owner_user_id.value),
                    "profileType": profile_type.value,
                },
            )
        )
        return profile

    # --- query -----------------------------------------------------------------------------------

    async def get_profile(self, profile_id: BusinessProfileId) -> BusinessProfile:
        profile = await self._profiles.get_by_id(profile_id)
        if profile is None:
            raise ProfileNotFoundError(profile_id)
        return profile

    async def list_my_profiles(
        self, owner_user_id: UserId, *, cursor: str | None, limit: int
    ) -> tuple[list[BusinessProfile], str | None]:
        return await self._profiles.list_by_owner(owner_user_id, cursor=cursor, limit=limit)

    async def list_public_profiles(
        self,
        *,
        profile_type: ProfileType | None,
        verified_only: bool,
        cursor: str | None,
        limit: int,
        main_category: MainCategory | None = None,
    ) -> tuple[list[BusinessProfile], str | None]:
        return await self._profiles.list_public(
            profile_type=profile_type,
            main_category=main_category,
            verified_only=verified_only,
            cursor=cursor,
            limit=limit,
        )

    async def get_public_profile_by_slug(self, slug: str, *, now: datetime) -> BusinessProfile:
        """ADR-0010. `getBusinessProfileBySlug` -- unlike `get_profile` (by-id, used by the
        owner's own dashboard), this 404s (`ProfileNotPubliclyVisibleError`) whenever the
        profile is not currently entitled (no trial, trial lapsed, subscription lapsed), so a
        lapsed org's public landing page actually disappears from the site rather than staying
        reachable by a stale/shared link."""
        profile = await self._profiles.get_by_slug(slug)
        if profile is None:
            raise ProfileNotPubliclyVisibleError(slug)
        status, _ = await self.get_subscription_status(profile.id, now=now)
        if status != "ACTIVE":
            raise ProfileNotPubliclyVisibleError(slug)
        return profile

    # --- update / archive (FR-PROF-002) ------------------------------------------------------

    async def update_profile(
        self,
        profile_id: BusinessProfileId,
        *,
        owner_user_id: UserId,
        name: LocalizedText | None,
        description: LocalizedText | None,
        contacts: dict[str, Any] | None,
        address: str | None,
        now: datetime,
        main_category: MainCategory | None = None,
    ) -> BusinessProfile:
        profile = await self.get_profile(profile_id)
        _check_owner(profile, owner_user_id)
        updated = profile.update_details(
            name=name,
            description=description,
            contacts=contacts,
            address=address,
            main_category=main_category,
            now=now,
        )
        return await self._profiles.save(updated)

    async def update_branding(
        self,
        profile_id: BusinessProfileId,
        *,
        owner_user_id: UserId,
        logo_media_asset_id: UUID | None,
        banner_media_asset_id: UUID | None,
        now: datetime,
    ) -> BusinessProfile:
        """Validates each asset id against `media` the same way `add_portfolio_item` does
        (`MediaAssetNotFoundError` otherwise) -- `None` skips validation for that one field
        (clearing it, not replacing it with an asset)."""
        profile = await self.get_profile(profile_id)
        _check_owner(profile, owner_user_id)
        for asset_id in (logo_media_asset_id, banner_media_asset_id):
            if asset_id is None:
                continue
            if await self._media.get_media_asset(asset_id) is None:
                raise MediaAssetNotFoundError(asset_id)
        updated = profile.update_branding(
            logo_media_asset_id=logo_media_asset_id,
            banner_media_asset_id=banner_media_asset_id,
            now=now,
        )
        return await self._profiles.save(updated)

    async def archive_profile(
        self, profile_id: BusinessProfileId, *, owner_user_id: UserId, now: datetime
    ) -> BusinessProfile:
        profile = await self.get_profile(profile_id)
        _check_owner(profile, owner_user_id)
        archived = profile.archive(now=now)
        return await self._profiles.save(archived)

    # --- onboarding / trial (ADR-0010) ----------------------------------------------------------

    async def complete_onboarding(
        self, profile_id: BusinessProfileId, *, owner_user_id: UserId, now: datetime
    ) -> BusinessProfile:
        """`BusinessProfile.complete_onboarding` does the mandatory-field + one-time-transition
        checks; this use case additionally writes the trial grant into
        `subscription_entitlement_projection` (the same table/write path
        `apply_subscription_projection` uses for a paid entitlement, called directly here rather
        than round-tripped through profiles' own outbox, since both writes land in the same
        transaction on the same aggregate) and appends `TrialSubscriptionStarted` for catalog to
        consume asynchronously."""
        assert self._subscriptions is not None
        profile = await self.get_profile(profile_id)
        _check_owner(profile, owner_user_id)
        updated = profile.complete_onboarding(now=now)
        saved = await self._profiles.save(updated)
        trial_entitlement_id = uuid4()
        event_id = uuid4()
        await self._subscriptions.upsert(
            SubscriptionEligibilitySnapshot(
                business_profile_id=saved.id,
                entitlement_id=trial_entitlement_id,
                valid_from=updated.trial_starts_at,  # type: ignore[arg-type]
                valid_until=updated.trial_ends_at,  # type: ignore[arg-type]
                activation_state="ACTIVE",
                source_event_id=event_id,
            )
        )
        await self._outbox.append(
            TrialSubscriptionStarted(
                event_id=event_id,
                occurred_at=now,
                actor=owner_user_id.value,
                aggregate_type="BusinessProfile",
                aggregate_id=saved.id.value,
                payload={
                    "ownerProfileId": str(saved.id.value),
                    "trialEntitlementId": str(trial_entitlement_id),
                    "validFrom": updated.trial_starts_at.isoformat(),  # type: ignore[union-attr]
                    "validUntil": updated.trial_ends_at.isoformat(),  # type: ignore[union-attr]
                },
            )
        )
        return saved

    async def sweep_expired_trials(self, *, now: datetime, batch_size: int) -> int:
        """Called by `infrastructure.worker.TrialExpiryWorker`. For each candidate from
        `BusinessProfileRepository.list_trials_expiring` (already scoped to "the projection row
        is still the trial grant, not since superseded by a paid purchase"), flips that
        projection row to `EXPIRED` and appends `TrialSubscriptionEnded` -- does not touch the
        `BusinessProfile` aggregate itself (`onboarding_completed_at`/`trial_starts_at`/
        `trial_ends_at` are a historical record of the trial that was granted, not a live
        entitlement state, so nothing on the aggregate changes). Mirrors
        `sweep_expired_badges`'s own shape."""
        assert self._subscriptions is not None
        candidates = await self._profiles.list_trials_expiring(now=now, limit=batch_size)
        swept = 0
        for profile in candidates:
            snapshot = await self._subscriptions.get_for_profile(profile.id)
            assert snapshot is not None  # guaranteed by list_trials_expiring's own join
            event_id = uuid4()
            await self._subscriptions.upsert(
                SubscriptionEligibilitySnapshot(
                    business_profile_id=profile.id,
                    entitlement_id=snapshot.entitlement_id,
                    valid_from=snapshot.valid_from,
                    valid_until=snapshot.valid_until,
                    activation_state="EXPIRED",
                    source_event_id=event_id,
                )
            )
            await self._outbox.append(
                TrialSubscriptionEnded(
                    event_id=event_id,
                    occurred_at=now,
                    actor=None,
                    aggregate_type="BusinessProfile",
                    aggregate_id=profile.id.value,
                    payload={
                        "ownerProfileId": str(profile.id.value),
                        "trialEntitlementId": str(snapshot.entitlement_id),
                        "validFrom": snapshot.valid_from.isoformat(),
                        "validUntil": snapshot.valid_until.isoformat(),
                    },
                )
            )
            swept += 1
        return swept

    # --- owner-admin-panel-invoked commands (`profiles:profile:manage`) ------------------------

    async def list_admin_profiles(
        self, *, status: str | None, cursor: str | None, limit: int
    ) -> tuple[list[BusinessProfile], str | None]:
        """adminListBusinessProfiles. No ownership scoping -- the caller has already authorized
        itself against `profiles:profile:manage` before invoking this (see
        `interfaces/auth.py::ActingProfileManager`)."""
        return await self._profiles.list_admin(status=status, cursor=cursor, limit=limit)

    async def count_profiles(self) -> int:
        return await self._profiles.count_all()

    async def admin_archive_profile(
        self, profile_id: BusinessProfileId, *, now: datetime
    ) -> BusinessProfile:
        """adminArchiveBusinessProfile. No ownership check, same end state as
        `moderation_archive_profile` below -- but that method is reserved for the future
        moderation module's own reactive, case-driven call path (`profiles:profile:moderate`);
        this one is the owner-admin panel's direct, `profiles:profile:manage`-gated equivalent."""
        profile = await self.get_profile(profile_id)
        archived = profile.archive(now=now)
        return await self._profiles.save(archived)

    # --- moderation-invoked commands (exposed via interfaces/moderation_port.py) -----------------

    async def moderation_archive_profile(
        self, profile_id: BusinessProfileId, *, now: datetime
    ) -> BusinessProfile:
        """No ownership check -- the caller has already authorized itself against a moderation
        permission key before invoking this (see `interfaces/moderation_port.py`'s own
        docstring, mirroring `catalog.interfaces.moderation_port.ListingModerationPort`)."""
        profile = await self.get_profile(profile_id)
        archived = profile.archive(now=now)
        return await self._profiles.save(archived)

    async def moderation_revoke_badge(
        self, profile_id: BusinessProfileId, *, now: datetime
    ) -> BusinessProfile:
        profile = await self.get_profile(profile_id)
        revoked = profile.revoke_badge(now=now)
        saved = await self._profiles.save(revoked)
        await self._outbox.append(
            VerifiedBadgeExpired(
                event_id=uuid4(),
                occurred_at=now,
                actor=None,
                aggregate_type="BusinessProfile",
                aggregate_id=saved.id.value,
                payload={"businessProfileId": str(saved.id.value)},
            )
        )
        return saved

    # --- badge expiry sweep (FR-PROF-006/007) ------------------------------------------------

    async def expire_badge(
        self, profile_id: BusinessProfileId, *, now: datetime
    ) -> BusinessProfile:
        """Called by the expiry sweep worker (`infrastructure.worker.BadgeExpiryWorker`), never a
        request-path use case."""
        profile = await self.get_profile(profile_id)
        expired = profile.expire_badge(now=now)
        saved = await self._profiles.save(expired)
        await self._outbox.append(
            VerifiedBadgeExpired(
                event_id=uuid4(),
                occurred_at=now,
                actor=None,
                aggregate_type="BusinessProfile",
                aggregate_id=saved.id.value,
                payload={"businessProfileId": str(saved.id.value)},
            )
        )
        return saved

    async def sweep_expired_badges(self, *, now: datetime, batch_size: int) -> int:
        """Called by `infrastructure.worker.BadgeExpiryWorker`. Returns the number of badges
        swept (state-transition + outbox event append committed together, DB Architecture Sec
        1.3's second sanctioned synchronous exception), mirroring `catalog.application.
        listing_use_cases.ListingUseCases.sweep_expired`'s own shape."""
        candidates = await self._profiles.list_badges_expiring(now=now, limit=batch_size)
        swept = 0
        for profile in candidates:
            await self.expire_badge(profile.id, now=now)
            swept += 1
        return swept

    # --- portfolio (FR-PROF-002) ---------------------------------------------------------------

    async def add_portfolio_item(
        self,
        profile_id: BusinessProfileId,
        *,
        owner_user_id: UserId,
        media_asset_id: UUID,
        caption: LocalizedText | None,
        now: datetime,
    ) -> BusinessProfile:
        profile = await self.get_profile(profile_id)
        _check_owner(profile, owner_user_id)
        asset = await self._media.get_media_asset(media_asset_id)
        if asset is None:
            raise MediaAssetNotFoundError(media_asset_id)
        updated = profile.add_portfolio_item(
            item_id=uuid4(), media_asset_id=media_asset_id, caption=caption, now=now
        )
        return await self._profiles.save(updated)

    async def remove_portfolio_item(
        self,
        profile_id: BusinessProfileId,
        item_id: UUID,
        *,
        owner_user_id: UserId,
        now: datetime,
    ) -> BusinessProfile:
        profile = await self.get_profile(profile_id)
        _check_owner(profile, owner_user_id)
        updated = profile.remove_portfolio_item(item_id, now=now)
        return await self._profiles.save(updated)

    async def list_portfolio(self, profile_id: BusinessProfileId) -> tuple[Any, ...]:
        profile = await self.get_profile(profile_id)
        return profile.portfolio

    # --- promo video (landing-page promo-video business rule, additive) ------------------------

    async def add_promo_video(
        self,
        profile_id: BusinessProfileId,
        *,
        owner_user_id: UserId,
        media_asset_id: UUID,
        now: datetime,
    ) -> BusinessProfile:
        """`profile.add_promo_video` enforces the aggregate-local "at most `MAX_PROMO_VIDEOS`"
        invariant; everything here is a fact about the referenced media asset that only this
        layer can read (`MediaAssetReaderPort`): it must exist, have finished scanning CLEAN
        (unlike a portfolio image, a rejected/still-pending video is never attached at all --
        there's no async removal-on-rejection projection for promo videos to fall back on), be
        video-typed, and be 30 seconds or shorter. Fails CLOSED on an unreadable duration
        (`duration_seconds is None`) -- a hand-rolled, dependency-free MP4/WebM parser
        (`media.infrastructure.video_probe`) is deliberately conservative about what it claims to
        know, and "cannot confirm this video is within the cap" must not be treated the same as
        "confirmed within the cap" for a rule the site owner asked to be mandatory."""
        profile = await self.get_profile(profile_id)
        _check_owner(profile, owner_user_id)
        asset = await self._media.get_media_asset(media_asset_id)
        if asset is None:
            raise MediaAssetNotFoundError(media_asset_id)
        if asset.scan_status != "CLEAN":
            raise PromoVideoNotReadyError(media_asset_id)
        if asset.content_type not in _PROMO_VIDEO_CONTENT_TYPES:
            raise PromoVideoNotVideoError(media_asset_id, asset.content_type)
        if (
            asset.duration_seconds is None
            or asset.duration_seconds > MAX_PROMO_VIDEO_DURATION_SECONDS
        ):
            raise PromoVideoTooLongError(
                media_asset_id, asset.duration_seconds, MAX_PROMO_VIDEO_DURATION_SECONDS
            )
        updated = profile.add_promo_video(media_asset_id=media_asset_id, now=now)
        return await self._profiles.save(updated)

    async def remove_promo_video(
        self,
        profile_id: BusinessProfileId,
        media_asset_id: UUID,
        *,
        owner_user_id: UserId,
        now: datetime,
    ) -> BusinessProfile:
        profile = await self.get_profile(profile_id)
        _check_owner(profile, owner_user_id)
        updated = profile.remove_promo_video(media_asset_id, now=now)
        return await self._profiles.save(updated)

    # --- subscription entitlement projection (Monetization task) ------------------------------

    async def apply_subscription_projection(
        self, snapshot: SubscriptionEligibilitySnapshot
    ) -> None:
        """Idempotent upsert of a projected billing `ACTIVE_SUBSCRIPTION` entitlement -- called by
        `infrastructure.event_projection.handle_subscription_entitlement_event`, wrapped in its
        own `idempotent_consume` ledger check against the *producing* billing event's own
        `event_id`. Mirrors `VerificationUseCases.apply_entitlement_projection`'s own one-line
        shape exactly."""
        assert self._subscriptions is not None
        await self._subscriptions.upsert(snapshot)

    async def get_subscription_status(
        self, profile_id: BusinessProfileId, *, now: datetime
    ) -> tuple[SubscriptionStatus, datetime | None]:
        """`("NONE", None)` -- never purchased a subscription -- and `("EXPIRED", valid_until)`
        are both "not currently entitled"; kept distinct so the dashboard can say "obuna hali
        yo'q" vs. "obuna muddati o'tgan, yangilang" rather than one generic message. A `REVOKED`
        snapshot reads the same as `EXPIRED` here (both are "not entitled now"); the distinction
        only matters to billing's own admin tooling, not to this read."""
        if self._subscriptions is None:
            return "NONE", None
        snapshot = await self._subscriptions.get_for_profile(profile_id)
        if snapshot is None:
            return "NONE", None
        if snapshot.activation_state == "ACTIVE" and snapshot.valid_until > now:
            return "ACTIVE", snapshot.valid_until
        return "EXPIRED", snapshot.valid_until

    # --- media asset-status projection (X-06) -----------------------------------------------------

    async def apply_portfolio_media_rejection(self, media_asset_id: UUID, *, now: datetime) -> None:
        """`MediaAssetRejected` projection: removes the portfolio item referencing this asset, if
        any (idempotent no-op otherwise). Called by `infrastructure.event_projection`, wrapped in
        its own `idempotent_consume` ledger check."""
        profile = await self._profiles.get_by_portfolio_media_asset_id(media_asset_id)
        if profile is None:
            return
        updated = profile.remove_portfolio_item_for_media_asset(media_asset_id, now=now)
        if updated is profile:
            return
        await self._profiles.save(updated)


def _check_owner(profile: BusinessProfile, owner_user_id: UserId) -> None:
    if profile.owner_user_id != owner_user_id:
        raise NotProfileOwnerError(profile.id)


_SLUG_UNSAFE = re.compile(r"[^a-z0-9]+")


def _generate_slug(name: LocalizedText, profile_id: UUID) -> str:
    """Display-only routing, not an identity (Physical DB: "id-suffix resolved; not unique by
    design"), mirroring `catalog.domain.policies.generate_slug`'s own regex-based collapse
    (profiles may not statically import catalog, so the pattern is duplicated rather than
    shared). A plain `str.split()` only breaks on whitespace, so a name like "Oq Oltin MChJ #1"
    produced "oq-oltin-mchj-#1-..." -- a literal `#` in a URL path segment is a fragment
    delimiter, so any real `<a href>` built from it truncates there and never reaches the
    server. `_SLUG_UNSAFE` collapses every run of non-alphanumeric characters (not just
    whitespace) to one hyphen instead."""
    base = (name.uz_latn or name.ru or name.en or name.uz_cyrl or "profile").strip().lower()
    slug_base = _SLUG_UNSAFE.sub("-", base).strip("-") or "profile"
    return f"{slug_base}-{str(profile_id)[:8]}"
