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

from contracts.events.profiles import BusinessProfileCreated, VerifiedBadgeExpired
from profiles.application.exceptions import (
    MediaAssetNotFoundError,
    NotProfileOwnerError,
    ProfileNotFoundError,
)
from profiles.application.ports import (
    BusinessProfileRepository,
    MediaAssetReaderPort,
    SubscriptionEligibilityRepository,
    SubscriptionEligibilitySnapshot,
)
from profiles.domain import BusinessProfile, ProfileType
from shared_kernel import BusinessProfileId, LocalizedText, OutboxPort, UserId

SubscriptionStatus = Literal["ACTIVE", "EXPIRED", "NONE"]


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
    ) -> tuple[list[BusinessProfile], str | None]:
        return await self._profiles.list_public(
            profile_type=profile_type, verified_only=verified_only, cursor=cursor, limit=limit
        )

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
    ) -> BusinessProfile:
        profile = await self.get_profile(profile_id)
        _check_owner(profile, owner_user_id)
        updated = profile.update_details(
            name=name, description=description, contacts=contacts, address=address, now=now
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
