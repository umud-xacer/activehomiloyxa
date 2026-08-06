"""catalog/application -- `QuotaEnforcementService` (I-08). Enforces quotas from a *locally
projected* subscription snapshot only (`SubscriptionSnapshotRepository`, written solely by
`apply_entitlement_projection` from billing's own outbox events) -- catalog never imports billing
and never calls it synchronously (AIR-10 named cycle; DDD Sec 9 I-08). Also owns writing that
projection, since the two responsibilities share the one repository this service depends on."""

from __future__ import annotations

from catalog.application.ports import SubscriptionSnapshot, SubscriptionSnapshotRepository
from catalog.domain.exceptions import QuotaExceededError
from shared_kernel import BusinessProfileId

_MAX_ACTIVE_LISTINGS_KEY = "max_active_listings"


class QuotaEnforcementService:
    def __init__(self, *, subscriptions: SubscriptionSnapshotRepository) -> None:
        self._subscriptions = subscriptions

    async def check_can_create(
        self, *, owner_profile_id: BusinessProfileId | None, active_listing_count: int
    ) -> None:
        """A personal (non-business-profile) owner, or a business profile billing has never
        issued an entitlement for (no projected snapshot -- billing/BC-08 does not exist as of
        this task), is treated as unlimited in v1: quota enforcement can only ever be as strict
        as the entitlement data actually projected (see `SubscriptionSnapshot`'s own
        docstring)."""
        if owner_profile_id is None:
            return
        snapshot = await self._subscriptions.get_for_profile(owner_profile_id)
        if snapshot is None:
            return
        limit = snapshot.quota_document.get(_MAX_ACTIVE_LISTINGS_KEY)
        if limit is None:
            return
        if active_listing_count >= int(limit):
            raise QuotaExceededError(limit=int(limit), current=active_listing_count)

    async def apply_entitlement_projection(self, snapshot: SubscriptionSnapshot) -> None:
        """Called only by the idempotent billing-entitlement event consumer
        (`catalog/infrastructure`, wrapped in `backbone.idempotency.consumer.idempotent_consume`
        keyed on `snapshot.source_event_id`) -- this method itself is a plain upsert, not
        idempotency-aware on its own."""
        await self._subscriptions.upsert(snapshot)
