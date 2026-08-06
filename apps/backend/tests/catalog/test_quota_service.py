"""`catalog.application.QuotaEnforcementService` (I-08) -- unit-level coverage of the branches
`ListingUseCases.create_listing`'s own call site doesn't reach directly (calling
`check_can_create`/`apply_entitlement_projection` on the service itself, not through the use
case)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from catalog.application.ports import SubscriptionSnapshot
from catalog.application.quota_service import QuotaEnforcementService
from shared_kernel import BusinessProfileId

from .conftest import FakeSubscriptionSnapshotRepository

NOW = datetime(2026, 7, 11, tzinfo=UTC)


async def test_check_can_create_with_no_acting_profile_is_unlimited(
    fake_subscriptions: FakeSubscriptionSnapshotRepository,
) -> None:
    service = QuotaEnforcementService(subscriptions=fake_subscriptions)
    await service.check_can_create(
        owner_profile_id=None, active_listing_count=999
    )  # must not raise


async def test_check_can_create_snapshot_without_quota_key_is_unlimited(
    fake_subscriptions: FakeSubscriptionSnapshotRepository,
) -> None:
    owner_profile_id = BusinessProfileId(value=uuid4())
    fake_subscriptions.snapshots[owner_profile_id.value] = SubscriptionSnapshot(
        owner_profile_id=owner_profile_id,
        entitlement_id=uuid4(),
        product_definition_id=None,
        quota_document={},  # no "max_active_listings" key
        valid_until=None,
        source_event_id=uuid4(),
    )
    service = QuotaEnforcementService(subscriptions=fake_subscriptions)
    await service.check_can_create(owner_profile_id=owner_profile_id, active_listing_count=999)


async def test_apply_entitlement_projection_upserts_the_snapshot(
    fake_subscriptions: FakeSubscriptionSnapshotRepository,
) -> None:
    owner_profile_id = BusinessProfileId(value=uuid4())
    service = QuotaEnforcementService(subscriptions=fake_subscriptions)
    snapshot = SubscriptionSnapshot(
        owner_profile_id=owner_profile_id,
        entitlement_id=uuid4(),
        product_definition_id=None,
        quota_document={"max_active_listings": 3},
        valid_until=None,
        source_event_id=uuid4(),
    )

    await service.apply_entitlement_projection(snapshot)

    stored = await fake_subscriptions.get_for_profile(owner_profile_id)
    assert stored is not None
    assert stored.quota_document["max_active_listings"] == 3
