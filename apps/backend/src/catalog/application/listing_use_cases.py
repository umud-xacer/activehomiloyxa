"""catalog/application -- `ListingUseCases` (Task P-07): create/draft, image attach/detach/
reorder, publish, edit, the `changeListingStatus` transition dispatch (suspend/archive/restore/
renew/delete), the expiry sweep, query (detail/owner/public listings/statistics), the media
asset-status projection, and the moderation-invoked unflag command. Every method takes the
caller's own resolved `UserId`/`BusinessProfileId | None` -- authorization (a valid session) is
resolved by the router via `ActingUser` before any of these run, the same self-service trust
boundary `media.application.intake_use_cases.MediaIntakeUseCases` documents for its own callers;
ownership beyond "is authenticated" is checked here via `catalog.domain.exceptions.
NotListingOwnerError`. State transition + outbox event append happen on the same session before
one commit (DB Architecture Sec 1.3's second sanctioned synchronous exception; the caller
-- `infrastructure/` -- owns the transaction boundary, this layer just calls both in order)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from catalog.application.duplicate_detection_service import DuplicateDetectionService
from catalog.application.exceptions import (
    CategoryFormUnavailableError,
    CategoryNotFoundError,
    ListingMediaAssetNotFoundError,
    ListingNotFoundError,
    StaleListingVersionError,
)
from catalog.application.ports import (
    CategoryFormPort,
    ListingRepository,
    MediaAssetReaderPort,
    PlatformSettingsReaderPort,
)
from catalog.application.quota_service import QuotaEnforcementService
from catalog.domain.exceptions import NotListingOwnerError
from catalog.domain.image_attachment import ImageAttachment
from catalog.domain.listing import Listing
from catalog.domain.policies import generate_slug, validate_attribute_set
from catalog.domain.value_objects import (
    ImageStatus,
    LifecycleState,
    ListingType,
    PromotionKind,
)
from contracts.events.catalog import (
    ListingArchived,
    ListingCreated,
    ListingDeleted,
    ListingDraftSaved,
    ListingEdited,
    ListingExpired,
    ListingFlagged,
    ListingPublished,
    ListingRenewed,
    ListingSuspended,
    ListingViewed,
)
from shared_kernel import (
    BusinessProfileId,
    EventEnvelope,
    GeoLocation,
    ListingId,
    Money,
    OutboxPort,
    UserId,
)

_StatusAction = str
"""`ListingStatusChangeRequest.action`: one of PUBLISH/ARCHIVE/SUSPEND/RENEW/RESTORE/DELETE
(`interfaces/dto.py`'s own closed literal) -- kept as `str` here to avoid this application module
importing the interfaces-layer DTO (Clean Architecture rule 4 runs the other way)."""

_SUBSCRIPTION_LAPSE_REASON = "subscription_lapsed"
"""The fixed `LifecycleTransitionRecord.reason` a subscription-lapse-driven `suspend()` always
carries -- `reactivate_all_by_owner_profile`'s own marker to distinguish its suspensions from
any other (moderation, owner-initiated) so a renewal never restores the wrong ones."""
_SUBSCRIPTION_RENEWAL_REASON = "subscription_renewed"


class ListingUseCases:
    def __init__(
        self,
        *,
        listings: ListingRepository,
        categories: CategoryFormPort,
        settings: PlatformSettingsReaderPort,
        media: MediaAssetReaderPort,
        outbox: OutboxPort,
        quota: QuotaEnforcementService,
        duplicates: DuplicateDetectionService,
    ) -> None:
        self._listings = listings
        self._categories = categories
        self._settings = settings
        self._media = media
        self._outbox = outbox
        self._quota = quota
        self._duplicates = duplicates

    # --- creation (FR-ADV-001/002/003, I-07/I-08) ----------------------------------------------

    async def create_listing(
        self,
        *,
        owner_user_id: UserId,
        owner_profile_id: BusinessProfileId | None,
        listing_type: ListingType,
        category_id: UUID,
        title: str,
        description: str | None,
        attributes: dict[str, Any],
        price: Money | None,
        location: GeoLocation | None,
        image_media_asset_ids: list[UUID] | None,
        publish: bool,
        requires_payment: bool = False,
        now: datetime,
    ) -> Listing:
        category = await self._categories.get_category(category_id)
        if category is None or category.status != "ACTIVE":
            raise CategoryNotFoundError(category_id)
        binding = await self._categories.get_current_form_binding(category_id)
        if binding is None:
            raise CategoryFormUnavailableError(category_id)

        if owner_profile_id is not None:
            active_count = await self._listings.count_active_by_owner_profile(
                owner_profile_id
            )
            await self._quota.check_can_create(
                owner_profile_id=owner_profile_id, active_listing_count=active_count
            )

        image_ids = image_media_asset_ids or []
        validate_attribute_set(
            attributes,
            binding.specs,
            image_count=len(image_ids),
            field_codes=binding.field_codes,
        )

        listing_id = ListingId(value=uuid4())
        listing = Listing.create(
            listing_id=listing_id,
            record_id=uuid4(),
            listing_type=listing_type,
            owner_user_id=owner_user_id,
            owner_profile_id=owner_profile_id,
            category_id=category_id,
            category_path=category.path,
            form_definition_id=binding.form_definition_id,
            form_definition_version_id=binding.form_definition_version_id,
            title=title,
            description=description,
            attributes=attributes,
            price=price,
            location=location,
            slug=generate_slug(title, listing_id.value),
            now=now,
        )
        if requires_payment:
            listing = listing.mark_awaiting_payment(now=now)

        for media_asset_id in image_ids:
            listing = await self._attach_verified_image(
                listing, media_asset_id=media_asset_id, now=now
            )

        is_duplicate = await self._duplicates.is_likely_duplicate(
            owner_user_id=owner_user_id, category_id=category_id, title=title
        )
        if is_duplicate:
            listing = listing.flag(
                record_id=uuid4(), reason="duplicate-detection", now=now
            )

        await self._listings.add(listing)
        await self._publish(
            ListingCreated(
                event_id=uuid4(),
                occurred_at=now,
                actor=owner_user_id.value,
                aggregate_type="Listing",
                aggregate_id=listing.id.value,
                payload=await self._listing_payload(listing),
            )
        )
        if is_duplicate:
            await self._publish(
                ListingFlagged(
                    event_id=uuid4(),
                    occurred_at=now,
                    actor=None,
                    aggregate_type="Listing",
                    aggregate_id=listing.id.value,
                    payload=await self._listing_payload(
                        listing, reason="duplicate-detection"
                    ),
                )
            )

        # Listing paywall (2026-08-23): `publish=True` under `requires_payment=True` defers the
        # publish intent rather than dropping it -- `activate_after_payment` below is the only
        # path that ever calls `_do_publish` on an `awaiting_payment` listing, once billing's
        # `EntitlementActivated` (`entitlementType=LISTING_PUBLICATION`) confirms it was paid for.
        if publish and not requires_payment:
            listing = await self._do_publish(
                listing, actor_user_id=owner_user_id, now=now
            )
        else:
            await self._publish(
                ListingDraftSaved(
                    event_id=uuid4(),
                    occurred_at=now,
                    actor=owner_user_id.value,
                    aggregate_type="Listing",
                    aggregate_id=listing.id.value,
                    payload=await self._listing_payload(listing),
                )
            )
        return listing

    async def _attach_verified_image(
        self, listing: Listing, *, media_asset_id: UUID, now: datetime
    ) -> Listing:
        """Existence-only check (`catalog.application.ports.MediaAssetSnapshot`'s own docstring:
        no sanctioned way to verify the caller uploaded this specific asset).

        The snapshot's `scan_status` seeds the attachment rather than being discarded: see
        `Listing.attach_image` for why an attachment created PENDING for an already-scanned asset
        never recovered."""
        snapshot = await self._media.get_media_asset(media_asset_id)
        if snapshot is None:
            raise ListingMediaAssetNotFoundError(media_asset_id)
        return listing.attach_image(
            image_id=uuid4(),
            media_asset_id=media_asset_id,
            now=now,
            status=ImageStatus(snapshot.scan_status),
        )

    # --- images (I-04) --------------------------------------------------------------------------

    async def attach_image(
        self,
        *,
        listing_id: ListingId,
        actor_user_id: UserId,
        media_asset_id: UUID,
        now: datetime,
    ) -> ImageAttachment:
        listing = await self._require_owned(listing_id, actor_user_id)
        listing = await self._attach_verified_image(
            listing, media_asset_id=media_asset_id, now=now
        )
        listing = await self._listings.save(listing)
        return listing.images[-1]

    async def detach_image(
        self,
        *,
        listing_id: ListingId,
        actor_user_id: UserId,
        image_id: UUID,
        now: datetime,
    ) -> None:
        listing = await self._require_owned(listing_id, actor_user_id)
        listing = listing.detach_image(image_id, now=now)
        listing = await self._listings.save(listing)

    async def reorder_images(
        self,
        *,
        listing_id: ListingId,
        actor_user_id: UserId,
        ordered_image_ids: tuple[UUID, ...],
        now: datetime,
    ) -> tuple[ImageAttachment, ...]:
        listing = await self._require_owned(listing_id, actor_user_id)
        listing = listing.reorder_images(ordered_image_ids, now=now)
        listing = await self._listings.save(listing)
        return listing.images

    async def list_images(self, listing_id: ListingId) -> tuple[ImageAttachment, ...]:
        listing = await self._require_listing(listing_id)
        return listing.images

    # --- publish / edit --------------------------------------------------------------------------

    async def publish_listing(
        self, *, listing_id: ListingId, actor_user_id: UserId, now: datetime
    ) -> Listing:
        listing = await self._require_owned(listing_id, actor_user_id)
        return await self._do_publish(listing, actor_user_id=actor_user_id, now=now)

    async def _do_publish(
        self, listing: Listing, *, actor_user_id: UserId, now: datetime
    ) -> Listing:
        settings = await self._settings.get_catalog_settings()
        expires_at = now + timedelta(days=settings.default_expiry_days)
        listing = listing.publish(
            record_id=uuid4(),
            actor_user_id=actor_user_id.value,
            expires_at=expires_at,
            now=now,
        )
        listing = await self._listings.save(listing)
        await self._publish(
            ListingPublished(
                event_id=uuid4(),
                occurred_at=now,
                actor=actor_user_id.value,
                aggregate_type="Listing",
                aggregate_id=listing.id.value,
                payload=await self._listing_payload(listing),
            )
        )
        return listing

    async def edit_listing(
        self,
        *,
        listing_id: ListingId,
        actor_user_id: UserId,
        expected_lock_version: int,
        title: str | None,
        description: str | None,
        attributes: dict[str, Any] | None,
        price: Money | None,
        location: GeoLocation | None,
        now: datetime,
    ) -> Listing:
        listing = await self._require_owned(listing_id, actor_user_id)
        if listing.lock_version != expected_lock_version:
            raise StaleListingVersionError(
                listing_id, expected=expected_lock_version, actual=listing.lock_version
            )
        binding = await self._categories.get_current_form_binding(listing.category_id)
        if binding is None:
            raise CategoryFormUnavailableError(listing.category_id)
        merged_attributes = attributes if attributes is not None else listing.attributes
        validate_attribute_set(
            merged_attributes,
            binding.specs,
            image_count=len(listing.images),
            field_codes=binding.field_codes,
        )

        listing = listing.edit_content(
            record_id=uuid4(),
            actor_user_id=actor_user_id.value,
            now=now,
            form_definition_id=binding.form_definition_id,
            form_definition_version_id=binding.form_definition_version_id,
            title=title,
            description=description,
            attributes=attributes,
            price=price,
            location=location,
        )
        listing = await self._listings.save(listing)
        await self._publish(
            ListingEdited(
                event_id=uuid4(),
                occurred_at=now,
                actor=actor_user_id.value,
                aggregate_type="Listing",
                aggregate_id=listing.id.value,
                payload=await self._listing_payload(listing),
            )
        )
        return listing

    # --- status transitions (changeListingStatus) -------------------------------------------------

    async def change_status(
        self,
        *,
        listing_id: ListingId,
        actor_user_id: UserId,
        action: _StatusAction,
        reason: str | None,
        now: datetime,
    ) -> Listing:
        listing = await self._require_owned(listing_id, actor_user_id)
        if action == "PUBLISH":
            return await self._do_publish(listing, actor_user_id=actor_user_id, now=now)
        if action == "SUSPEND":
            listing = listing.suspend(
                record_id=uuid4(),
                actor_user_id=actor_user_id.value,
                reason=reason,
                now=now,
            )
            listing = await self._listings.save(listing)
            await self._publish(
                ListingSuspended(
                    event_id=uuid4(),
                    occurred_at=now,
                    actor=actor_user_id.value,
                    aggregate_type="Listing",
                    aggregate_id=listing.id.value,
                    payload=await self._listing_payload(listing, reason=reason),
                )
            )
            return listing
        if action == "ARCHIVE":
            listing = listing.archive(
                record_id=uuid4(),
                actor_user_id=actor_user_id.value,
                reason=reason,
                now=now,
            )
            listing = await self._listings.save(listing)
            await self._publish(
                ListingArchived(
                    event_id=uuid4(),
                    occurred_at=now,
                    actor=actor_user_id.value,
                    aggregate_type="Listing",
                    aggregate_id=listing.id.value,
                    payload=await self._listing_payload(listing, reason=reason),
                )
            )
            return listing
        if action == "RESTORE":
            listing = listing.restore(
                record_id=uuid4(),
                actor_user_id=actor_user_id.value,
                reason=reason,
                now=now,
            )
            listing = await self._listings.save(listing)
            await self._publish(
                ListingPublished(
                    event_id=uuid4(),
                    occurred_at=now,
                    actor=actor_user_id.value,
                    aggregate_type="Listing",
                    aggregate_id=listing.id.value,
                    payload=await self._listing_payload(listing, reason=reason),
                )
            )
            return listing
        if action == "RENEW":
            settings = await self._settings.get_catalog_settings()
            new_expires_at = now + timedelta(days=settings.default_expiry_days)
            listing = listing.renew(
                record_id=uuid4(),
                actor_user_id=actor_user_id.value,
                new_expires_at=new_expires_at,
                now=now,
            )
            listing = await self._listings.save(listing)
            await self._publish(
                ListingRenewed(
                    event_id=uuid4(),
                    occurred_at=now,
                    actor=actor_user_id.value,
                    aggregate_type="Listing",
                    aggregate_id=listing.id.value,
                    payload=await self._listing_payload(listing),
                )
            )
            return listing
        if action == "DELETE":
            listing = listing.delete(
                record_id=uuid4(),
                actor_user_id=actor_user_id.value,
                reason=reason,
                now=now,
            )
            listing = await self._listings.save(listing)
            await self._publish(
                ListingDeleted(
                    event_id=uuid4(),
                    occurred_at=now,
                    actor=actor_user_id.value,
                    aggregate_type="Listing",
                    aggregate_id=listing.id.value,
                    payload=await self._listing_payload(listing, reason=reason),
                )
            )
            return listing
        raise ValueError(f"unsupported changeListingStatus action: {action!r}")

    async def delete_listing(
        self, *, listing_id: ListingId, actor_user_id: UserId, now: datetime
    ) -> None:
        """`deleteListing` (distinct HTTP operation from `changeListingStatus(action=DELETE)`,
        `contracts/openapi.yaml` -- both drive the same domain transition)."""
        await self.change_status(
            listing_id=listing_id,
            actor_user_id=actor_user_id,
            action="DELETE",
            reason=None,
            now=now,
        )

    # --- expiry sweep (FR-ADV-006/007, worker-only) ------------------------------------------------

    async def sweep_expired(self, *, now: datetime, batch_size: int) -> int:
        candidates = await self._listings.list_expiring(now=now, limit=batch_size)
        swept = 0
        for listing in candidates:
            before = len(listing.transitions)
            updated = listing.record_expiry(record_id=uuid4(), now=now)
            if len(updated.transitions) == before:
                continue
            updated = await self._listings.save(updated)
            await self._publish(
                ListingExpired(
                    event_id=uuid4(),
                    occurred_at=now,
                    actor=None,
                    aggregate_type="Listing",
                    aggregate_id=updated.id.value,
                    payload=await self._listing_payload(updated),
                )
            )
            swept += 1
        return swept

    # --- media asset-status projection (X-06) ------------------------------------------------------

    async def apply_media_status_projection(
        self, *, media_asset_id: UUID, status: ImageStatus, now: datetime
    ) -> None:
        """Called only by the idempotent media asset-status event consumer
        (`catalog/infrastructure`, wrapped in `backbone.idempotency.consumer.idempotent_consume`
        keyed on the media event's id) -- a no-op if no listing currently holds this attachment
        (`Listing.update_image_status`'s own redelivery-safe docstring)."""
        listing = await self._listings.get_by_image_media_asset_id(media_asset_id)
        if listing is None:
            return
        updated = listing.update_image_status(
            media_asset_id=media_asset_id, status=status, now=now
        )
        if updated is listing:
            return
        updated = await self._listings.save(updated)

    # --- listing paywall (2026-08-23, billing entitlement events) ----------------------------------

    async def activate_after_payment(
        self, *, listing_id: ListingId, now: datetime
    ) -> Listing:
        """billing's `EntitlementActivated` (`entitlementType=LISTING_PUBLICATION`) reaches
        catalog via `infrastructure.event_projection.handle_listing_publication_event` -- the ONLY
        caller that ever publishes a listing being held `awaiting_payment` (mirrors
        `apply_promotion_projection`'s own "billing event -> catalog projection" shape, X-03).
        Routes through the same `_do_publish` every direct-publish path uses, so a paid listing
        gets a real expiry term computed the same way (`Listing.publish` itself unconditionally
        clears `awaiting_payment` -- see its own docstring) -- a paid listing is not a
        second-class publish. Attributed to the listing's own owner: the payment was made on
        their behalf, and there is no acting user in an outbox consumer's own request scope."""
        listing = await self._require_listing(listing_id)
        return await self._do_publish(
            listing, actor_user_id=listing.owner_user_id, now=now
        )

    # --- promotion projection (DDD Sec 5.3 PromotionMarker; X-03, billing entitlement events) ------

    async def apply_promotion_projection(
        self,
        *,
        listing_id: ListingId,
        kind: PromotionKind,
        valid_until: datetime,
        entitlement_id: UUID,
        now: datetime,
    ) -> Listing:
        """P-20: billing's `EntitlementActivated` (`entitlementType=LISTING_PROMOTION`) reaches
        catalog via `infrastructure.event_projection.handle_listing_promotion_event` -- catalog
        never imports billing (AIR-10), the fact arrives via the outbox (X-03). Applies
        `Listing.apply_promotion` and republishes `ListingEdited` (not a new event type: the
        frozen catalogue has no dedicated "promotion changed" event, and a promotion change is,
        from every consumer's perspective, exactly a change to the listing's own public content)
        carrying the now-current `promotion` field so search's already-built `ListingEdited`
        consumer (`search.infrastructure.event_projection.handle_listing_edited`) picks it up
        through the ordinary listing-content channel, per the frozen event contract's own
        `EntitlementActivated` docstring ("Catalog (promotion/quota)")."""
        listing = await self._require_listing(listing_id)
        listing = listing.apply_promotion(
            kind=kind, valid_until=valid_until, entitlement_id=entitlement_id, now=now
        )
        listing = await self._listings.save(listing)
        await self._publish(
            ListingEdited(
                event_id=uuid4(),
                occurred_at=now,
                actor=None,
                aggregate_type="Listing",
                aggregate_id=listing.id.value,
                payload=await self._listing_payload(listing),
            )
        )
        return listing

    async def clear_promotion_projection(
        self, *, listing_id: ListingId, now: datetime
    ) -> Listing:
        """`EntitlementExpired`/`EntitlementRevoked` (`entitlementType=LISTING_PROMOTION`) --
        withdraws the projection the same way `apply_promotion_projection` applies it."""
        listing = await self._require_listing(listing_id)
        listing = listing.clear_promotion(now=now)
        listing = await self._listings.save(listing)
        await self._publish(
            ListingEdited(
                event_id=uuid4(),
                occurred_at=now,
                actor=None,
                aggregate_type="Listing",
                aggregate_id=listing.id.value,
                payload=await self._listing_payload(listing),
            )
        )
        return listing

    # --- moderation command port (unflag) ----------------------------------------------------------

    async def unflag_listing(
        self, *, listing_id: ListingId, reason: str | None, now: datetime
    ) -> Listing:
        """The moderation-invoked command (`catalog.domain.listing.Listing.unflag`'s own
        docstring): authorization (the caller holding `catalog:listing:moderate`) is the
        in-process caller's own responsibility via `identity.interfaces.ports.AuthorizationPort`
        -- exactly as `AuthorizationPort` itself is "consulted in-process by every other module"
        without re-validating inside the callee (`identity/interfaces/ports.py`'s own docstring).
        No dedicated event exists for `UNFLAG` in the frozen catalogue; only the transition is
        recorded (see `Listing.unflag`)."""
        listing = await self._require_listing(listing_id)
        listing = listing.unflag(record_id=uuid4(), reason=reason, now=now)
        listing = await self._listings.save(listing)
        return listing

    async def moderator_suspend_listing(
        self,
        *,
        listing_id: ListingId,
        moderator_user_id: UUID,
        reason: str | None,
        now: datetime,
    ) -> Listing:
        """Task P-12's own moderation command surface -- distinct from `change_status`'s own
        `SUSPEND` branch, which requires `_require_owned` (the owner-facing `changeListingStatus`
        operation); a moderator is never the listing's owner, so this skips that check entirely,
        the same "authorization is the in-process caller's own responsibility" trust boundary
        `unflag_listing` documents. Backs BOTH the `HIDE` and `SUSPEND` `ResolutionAction` verbs
        (catalog has one relevant "withhold from public view, reversible" transition; the verb
        distinction lives in `ModerationCase.resolutionAction`'s own audit record, not a second
        catalog-side state -- see `moderation/README.md` for the full verb-to-transition
        mapping rationale)."""
        listing = await self._require_listing(listing_id)
        listing = listing.suspend(
            record_id=uuid4(), actor_user_id=moderator_user_id, reason=reason, now=now
        )
        listing = await self._listings.save(listing)
        await self._publish(
            ListingSuspended(
                event_id=uuid4(),
                occurred_at=now,
                actor=moderator_user_id,
                aggregate_type="Listing",
                aggregate_id=listing.id.value,
                payload=await self._listing_payload(listing, reason=reason),
            )
        )
        return listing

    async def moderator_archive_listing(
        self,
        *,
        listing_id: ListingId,
        moderator_user_id: UUID,
        reason: str | None,
        now: datetime,
    ) -> Listing:
        """Backs the `REJECT` `ResolutionAction` verb -- catalog's `archive()` transition (a
        stronger, more final judgment than `suspend()`'s "withhold, reversible"), same
        no-ownership-check reasoning as `moderator_suspend_listing`."""
        listing = await self._require_listing(listing_id)
        listing = listing.archive(
            record_id=uuid4(), actor_user_id=moderator_user_id, reason=reason, now=now
        )
        listing = await self._listings.save(listing)
        await self._publish(
            ListingArchived(
                event_id=uuid4(),
                occurred_at=now,
                actor=moderator_user_id,
                aggregate_type="Listing",
                aggregate_id=listing.id.value,
                payload=await self._listing_payload(listing, reason=reason),
            )
        )
        return listing

    async def moderator_delete_listing(
        self,
        *,
        listing_id: ListingId,
        moderator_user_id: UUID,
        reason: str | None,
        now: datetime,
    ) -> Listing:
        """Backs the `REMOVE` `ResolutionAction` verb -- catalog's `delete()` transition (DM-06:
        "Deleted is a state, never a row removal"), same no-ownership-check reasoning as
        `moderator_suspend_listing`."""
        listing = await self._require_listing(listing_id)
        listing = listing.delete(
            record_id=uuid4(), actor_user_id=moderator_user_id, reason=reason, now=now
        )
        listing = await self._listings.save(listing)
        await self._publish(
            ListingDeleted(
                event_id=uuid4(),
                occurred_at=now,
                actor=moderator_user_id,
                aggregate_type="Listing",
                aggregate_id=listing.id.value,
                payload=await self._listing_payload(listing, reason=reason),
            )
        )
        return listing

    async def suspend_all_by_owner(
        self, *, owner_user_id: UserId, reason: str | None, now: datetime
    ) -> int:
        """DB Architecture Sec 14.4's own worked example: "account suspension -> listings hidden
        by catalog's own transition" -- a compensation (X-04 style), never a cascade written by
        another module. Called by `infrastructure.event_projection.handle_identity_event`
        reacting to identity's own `AccountSuspended` event; catalog owns this reaction entirely
        (identity never reaches into catalog's schema, and moderation never writes catalog's
        tables either -- both would-be shortcuts this method exists to make unnecessary). Only
        currently-visible listings are suspended (`PUBLISHED`/`EDITED`) -- an already-`DRAFT`/
        `SUSPENDED`/`ARCHIVED`/`DELETED` listing has nothing further to withhold. Returns the
        count suspended, for the idempotent consumer's own logging."""
        suspended = 0
        cursor: str | None = None
        while True:
            listings, cursor = await self._listings.list_by_owner(
                owner_user_id, state=None, cursor=cursor, limit=50
            )
            if not listings:
                break
            for listing in listings:
                if listing.lifecycle_state not in (
                    LifecycleState.PUBLISHED,
                    LifecycleState.EDITED,
                ):
                    continue
                updated = listing.suspend(
                    record_id=uuid4(),
                    actor_user_id=owner_user_id.value,
                    reason=reason,
                    now=now,
                )
                updated = await self._listings.save(updated)
                await self._publish(
                    ListingSuspended(
                        event_id=uuid4(),
                        occurred_at=now,
                        actor=owner_user_id.value,
                        aggregate_type="Listing",
                        aggregate_id=updated.id.value,
                        payload=await self._listing_payload(updated, reason=reason),
                    )
                )
                suspended += 1
            if cursor is None:
                break
        return suspended

    async def suspend_all_by_owner_profile(
        self, *, owner_profile_id: BusinessProfileId, reason: str, now: datetime
    ) -> int:
        """Compensation for a lapsed `ACTIVE_SUBSCRIPTION` entitlement -- the business-profile-
        scoped sibling of `suspend_all_by_owner` above (same reasoning, DB Architecture Sec 14.4,
        just keyed by the profile a legal-entity account acted through rather than the account
        itself). Called by `infrastructure.event_projection.handle_subscription_visibility_event`
        reacting to billing's `EntitlementExpired`/`EntitlementRevoked` for `ACTIVE_SUBSCRIPTION`.
        `reason` is always `_SUBSCRIPTION_LAPSE_REASON` so `reactivate_all_by_owner_profile` can
        later tell a subscription-caused suspension apart from an unrelated one (moderation, the
        owner's own manual suspend) and never restore one of those by mistake. `actor_user_id=None`
        -- no acting user in scope, mirrors `record_expiry`'s own "system-driven" precedent."""
        suspended = 0
        cursor: str | None = None
        while True:
            listings, cursor = await self._listings.list_by_owner_profile(
                owner_profile_id, state=None, cursor=cursor, limit=50
            )
            if not listings:
                break
            for listing in listings:
                if listing.lifecycle_state not in (
                    LifecycleState.PUBLISHED,
                    LifecycleState.EDITED,
                ):
                    continue
                updated = listing.suspend(
                    record_id=uuid4(), actor_user_id=None, reason=reason, now=now
                )
                updated = await self._listings.save(updated)
                await self._publish(
                    ListingSuspended(
                        event_id=uuid4(),
                        occurred_at=now,
                        actor=None,
                        aggregate_type="Listing",
                        aggregate_id=updated.id.value,
                        payload=await self._listing_payload(updated, reason=reason),
                    )
                )
                suspended += 1
            if cursor is None:
                break
        return suspended

    async def reactivate_all_by_owner_profile(
        self, *, owner_profile_id: BusinessProfileId, now: datetime
    ) -> int:
        """Reverses `suspend_all_by_owner_profile` once the profile's subscription is active
        again (billing's `EntitlementActivated` for a renewal). Only restores listings whose most
        recent transition is THIS mechanism's own suspend (`reason == _SUBSCRIPTION_LAPSE_REASON`)
        -- a listing separately suspended for moderation stays suspended; this never overrides
        that call, the same "compensation, never a cascade" discipline the whole module follows."""
        reactivated = 0
        cursor: str | None = None
        while True:
            listings, cursor = await self._listings.list_by_owner_profile(
                owner_profile_id,
                state=LifecycleState.SUSPENDED.value,
                cursor=cursor,
                limit=50,
            )
            if not listings:
                break
            for listing in listings:
                if (
                    not listing.transitions
                    or listing.transitions[-1].reason != _SUBSCRIPTION_LAPSE_REASON
                ):
                    continue
                updated = listing.restore(
                    record_id=uuid4(),
                    actor_user_id=None,
                    reason=_SUBSCRIPTION_RENEWAL_REASON,
                    now=now,
                )
                updated = await self._listings.save(updated)
                await self._publish(
                    ListingPublished(
                        event_id=uuid4(),
                        occurred_at=now,
                        actor=None,
                        aggregate_type="Listing",
                        aggregate_id=updated.id.value,
                        payload=await self._listing_payload(
                            updated, reason=_SUBSCRIPTION_RENEWAL_REASON
                        ),
                    )
                )
                reactivated += 1
            if cursor is None:
                break
        return reactivated

    # --- queries -------------------------------------------------------------------------------

    async def get_listing(self, listing_id: ListingId) -> Listing:
        return await self._require_listing(listing_id)

    async def record_view(
        self, listing_id: ListingId, *, viewer_user_id: UserId | None, now: datetime
    ) -> None:
        """UNF-015/FR-ADV-010/DDD Sec 5.3 ViewRecordingPolicy: emits `ListingViewed` (frozen by
        ADR-0005, wired here per that ADR's own deferred "future task" -- the schema was already
        settled, only the producer call was outstanding). Called by `interfaces/routers.py::
        get_listing` AFTER its own I-06 visibility check passes, deliberately -- a caller who
        never actually saw the listing (blocked by visibility) must not count as a view."""
        event = ListingViewed(
            event_id=uuid4(),
            occurred_at=now,
            actor=viewer_user_id.value if viewer_user_id else None,
            aggregate_type="Listing",
            aggregate_id=listing_id.value,
            payload={
                "listingId": str(listing_id.value),
                "viewerUserId": str(viewer_user_id.value) if viewer_user_id else None,
            },
        )
        await self._outbox.append(event)

    async def list_my_listings(
        self,
        *,
        owner_user_id: UserId,
        state: str | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[Listing], str | None]:
        return await self._listings.list_by_owner(
            owner_user_id, state=state, cursor=cursor, limit=limit
        )

    async def list_public_listings(
        self,
        *,
        category_id: UUID | None,
        listing_type: str | None,
        cursor: str | None,
        limit: int,
        now: datetime,
    ) -> tuple[list[Listing], str | None]:
        return await self._listings.list_public(
            category_id=category_id,
            listing_type=listing_type,
            cursor=cursor,
            limit=limit,
            now=now,
        )

    # --- internal helpers ------------------------------------------------------------------------

    async def _require_listing(self, listing_id: ListingId) -> Listing:
        listing = await self._listings.get_by_id(listing_id)
        if listing is None:
            raise ListingNotFoundError(listing_id)
        return listing

    async def _require_owned(
        self, listing_id: ListingId, actor_user_id: UserId
    ) -> Listing:
        listing = await self._require_listing(listing_id)
        if listing.owner_user_id != actor_user_id:
            raise NotListingOwnerError(listing_id.value)
        return listing

    async def _primary_image_thumbnail_url(self, listing: Listing) -> str | None:
        """Delivery URL of the THUMBNAIL variant of the listing's first CLEAN image, by position.

        Resolved through the `MediaAssetReaderPort` this class already holds rather than derived
        from the ref: the variant's filename extension follows the source image's format
        (`thumbnail.png` for a PNG upload), so search -- which may not import `media` -- could
        only reconstruct it by guessing. Catalog forwards the URL on the event and stores nothing.

        `None` when the listing has no images, when none have cleared scanning yet, or when media
        cannot be reached -- all ordinary states that render the interface's existing placeholder.
        A media outage must never fail a publish (QR-05).
        """
        clean = [image for image in listing.images if image.status is ImageStatus.CLEAN]
        if not clean:
            return None
        primary = min(clean, key=lambda image: image.position)
        snapshot = await self._media.get_media_asset(primary.media_asset_id)
        return snapshot.thumbnail_url if snapshot else None

    async def _listing_payload(
        self, listing: Listing, *, reason: str | None = None
    ) -> dict[str, Any]:
        """P-20 fix (search/README.md's own "CONFIRMED payload gap blocking real content
        indexing", flagged and deliberately deferred by Task P-08): widened to carry every field
        `search.infrastructure.event_projection._upsert_content_from_payload` requires
        (DB Architecture Sec 3.5: "rebuilt from Catalog events: text fields...") -- title/
        description/categoryPath/listingType/attributes/price/location/slug/publishedAt, plus
        `ownerProfileId` and the current `promotion` projection (DDD Sec 5.3 `PromotionMarker`,
        X-03). Purely additive to the previously-shipped field set -- the five visibility-only
        search handlers and every OTHER consumer of catalog's outbox (messaging/notifications/
        moderation/analytics, `composition_root.make_catalog_outbox_fanout_handler`) read only
        the fields they already expect and ignore unknown extra keys, so this does not change
        their behaviour."""
        payload: dict[str, Any] = {
            "listingId": str(listing.id.value),
            "ownerUserId": str(listing.owner_user_id.value),
            "ownerProfileId": (
                str(listing.owner_profile_id.value)
                if listing.owner_profile_id
                else None
            ),
            "categoryId": str(listing.category_id),
            "categoryPath": listing.category_path,
            "listingType": listing.listing_type.value,
            "title": listing.title,
            "description": listing.description,
            "attributes": listing.attributes,
            "price": (
                {
                    "amount": str(listing.price.amount),
                    "currency": listing.price.currency,
                }
                if listing.price
                else None
            ),
            "location": (
                {
                    "latitude": listing.location.latitude,
                    "longitude": listing.location.longitude,
                }
                if listing.location
                else None
            ),
            "slug": listing.slug,
            "publishedAt": listing.published_at.isoformat()
            if listing.published_at
            else None,
            "lifecycleState": listing.lifecycle_state.value,
            "isFlagged": listing.is_flagged,
            "expiresAt": listing.expires_at.isoformat() if listing.expires_at else None,
            "promotion": (
                {
                    "kind": listing.promotion.kind.value,
                    "validUntil": listing.promotion.valid_until.isoformat(),
                    "entitlementId": str(listing.promotion.entitlement_id),
                }
                if listing.promotion
                else None
            ),
            # The lowest-positioned CLEAN image, as a bare `MediaAssetRef` (X-06: "Owners hold
            # MediaAssetRef only") -- search needs *something* to render a result thumbnail, and
            # `SearchHit.thumbnailUrl` has been in the frozen contract since P-01 while the read
            # model carried no image field at all, so every result card rendered a placeholder.
            # A ref, not a URL: catalog holds no storage key, and search turns the ref into a URL
            # through its own configured media base (`search.interfaces.routers`).
            # QUARANTINED/PENDING are excluded here rather than downstream so an unscanned or
            # rejected asset can never reach a public result card (I-04).
            "primaryImageThumbnailUrl": await self._primary_image_thumbnail_url(
                listing
            ),
        }
        if reason is not None:
            payload["reason"] = reason
        return payload

    async def _publish(
        self,
        event: EventEnvelope,
    ) -> None:
        await self._outbox.append(event)
