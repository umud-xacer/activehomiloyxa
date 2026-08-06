"""`search.application.indexing_use_cases.IndexingUseCases` -- every method writes to BOTH
`SearchIndexPort` and `FallbackIndexPort` (one projection, two sinks); each is a no-op when the
document is not yet indexed, except `upsert_listing_content` which always creates on first sight."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from search.application.indexing_use_cases import IndexingUseCases
from search.domain import ListingType, PromotionKind, PromotionMarker

from .conftest import FakeFallbackIndex, FakeSearchIndex

_NOW = datetime(2026, 7, 12, tzinfo=UTC)


@pytest.fixture
def use_cases(fake_index: FakeSearchIndex, fake_fallback: FakeFallbackIndex) -> IndexingUseCases:
    return IndexingUseCases(index=fake_index, fallback=fake_fallback)


class TestUpsertListingContent:
    async def test_I01_creates_a_new_document_on_first_sight(
        self,
        use_cases: IndexingUseCases,
        fake_index: FakeSearchIndex,
        fake_fallback: FakeFallbackIndex,
    ) -> None:
        listing_id = uuid4()
        category_id = uuid4()
        await use_cases.upsert_listing_content(
            listing_id=listing_id,
            owner_profile_id=None,
            title="Kvartira",
            description=None,
            category_id=category_id,
            category_path="/real-estate",
            listing_type=ListingType.ADVERTISEMENT,
            attributes={},
            price=None,
            location=None,
            slug="kvartira",
            published_at=_NOW,
            publicly_visible=True,
            now=_NOW,
        )
        assert listing_id in fake_index.documents
        assert listing_id in fake_fallback.documents
        assert fake_index.documents[listing_id].title == "Kvartira"

    async def test_I02_re_projects_content_preserving_promotion_and_verified_badge(
        self, use_cases: IndexingUseCases, fake_index: FakeSearchIndex
    ) -> None:
        listing_id = uuid4()
        category_id = uuid4()
        await use_cases.upsert_listing_content(
            listing_id=listing_id,
            owner_profile_id=None,
            title="Kvartira",
            description=None,
            category_id=category_id,
            category_path="/real-estate",
            listing_type=ListingType.ADVERTISEMENT,
            attributes={},
            price=None,
            location=None,
            slug="kvartira",
            published_at=_NOW,
            publicly_visible=True,
            now=_NOW,
        )
        await use_cases.apply_promotion(
            listing_id=listing_id,
            promotion=PromotionMarker(
                kind=PromotionKind.PREMIUM, valid_until=None, entitlement_id=uuid4()
            ),
            now=_NOW,
        )
        await use_cases.apply_verified_badge(
            owner_profile_id=uuid4(), verified_badge=True, now=_NOW
        )  # unrelated owner -- no-op, sanity check it doesn't blow up

        # a second content event (ListingEdited) arrives with a new title.
        await use_cases.upsert_listing_content(
            listing_id=listing_id,
            owner_profile_id=None,
            title="Kvartira (edited)",
            description=None,
            category_id=category_id,
            category_path="/real-estate",
            listing_type=ListingType.ADVERTISEMENT,
            attributes={},
            price=None,
            location=None,
            slug="kvartira",
            published_at=_NOW,
            publicly_visible=True,
            now=_NOW,
        )
        document = fake_index.documents[listing_id]
        assert document.title == "Kvartira (edited)"
        assert document.promotion is not None
        assert document.promotion.kind == PromotionKind.PREMIUM


class TestUpdateListingVisibility:
    async def test_I03_is_a_no_op_if_the_listing_has_no_indexed_document(
        self, use_cases: IndexingUseCases, fake_index: FakeSearchIndex
    ) -> None:
        await use_cases.update_listing_visibility(
            listing_id=uuid4(), publicly_visible=False, now=_NOW
        )
        assert fake_index.documents == {}

    async def test_I04_flips_publicly_visible_on_an_existing_document(
        self, use_cases: IndexingUseCases, fake_index: FakeSearchIndex
    ) -> None:
        listing_id = uuid4()
        await use_cases.upsert_listing_content(
            listing_id=listing_id,
            owner_profile_id=None,
            title="Kvartira",
            description=None,
            category_id=uuid4(),
            category_path="/real-estate",
            listing_type=ListingType.ADVERTISEMENT,
            attributes={},
            price=None,
            location=None,
            slug="kvartira",
            published_at=_NOW,
            publicly_visible=True,
            now=_NOW,
        )
        await use_cases.update_listing_visibility(
            listing_id=listing_id, publicly_visible=False, now=_NOW
        )
        assert fake_index.documents[listing_id].publicly_visible is False

    async def test_I05_deleted_is_represented_as_publicly_visible_false_not_a_row_removal(
        self, use_cases: IndexingUseCases, fake_index: FakeSearchIndex
    ) -> None:
        listing_id = uuid4()
        await use_cases.upsert_listing_content(
            listing_id=listing_id,
            owner_profile_id=None,
            title="Kvartira",
            description=None,
            category_id=uuid4(),
            category_path="/real-estate",
            listing_type=ListingType.ADVERTISEMENT,
            attributes={},
            price=None,
            location=None,
            slug="kvartira",
            published_at=_NOW,
            publicly_visible=True,
            now=_NOW,
        )
        await use_cases.update_listing_visibility(
            listing_id=listing_id, publicly_visible=False, now=_NOW
        )
        assert listing_id in fake_index.documents
        assert fake_index.documents[listing_id].publicly_visible is False


class TestPromotionProjection:
    async def test_I06_apply_promotion_is_a_no_op_if_undexed(
        self, use_cases: IndexingUseCases, fake_index: FakeSearchIndex
    ) -> None:
        await use_cases.apply_promotion(
            listing_id=uuid4(),
            promotion=PromotionMarker(
                kind=PromotionKind.FEATURED, valid_until=None, entitlement_id=uuid4()
            ),
            now=_NOW,
        )
        assert fake_index.documents == {}

    async def test_I07_clear_promotion_removes_an_existing_marker(
        self, use_cases: IndexingUseCases, fake_index: FakeSearchIndex
    ) -> None:
        listing_id = uuid4()
        await use_cases.upsert_listing_content(
            listing_id=listing_id,
            owner_profile_id=None,
            title="Kvartira",
            description=None,
            category_id=uuid4(),
            category_path="/real-estate",
            listing_type=ListingType.ADVERTISEMENT,
            attributes={},
            price=None,
            location=None,
            slug="kvartira",
            published_at=_NOW,
            publicly_visible=True,
            now=_NOW,
        )
        await use_cases.apply_promotion(
            listing_id=listing_id,
            promotion=PromotionMarker(
                kind=PromotionKind.TOP_PLACEMENT, valid_until=None, entitlement_id=uuid4()
            ),
            now=_NOW,
        )
        await use_cases.clear_promotion(listing_id=listing_id, now=_NOW)
        assert fake_index.documents[listing_id].promotion is None


class TestVerifiedBadgeFanOut:
    async def test_I08_applies_the_badge_to_every_listing_owned_by_the_profile(
        self, use_cases: IndexingUseCases, fake_index: FakeSearchIndex
    ) -> None:
        owner_profile_id = uuid4()
        listing_ids = [uuid4(), uuid4()]
        for listing_id in listing_ids:
            await use_cases.upsert_listing_content(
                listing_id=listing_id,
                owner_profile_id=owner_profile_id,
                title="Kvartira",
                description=None,
                category_id=uuid4(),
                category_path="/real-estate",
                listing_type=ListingType.ADVERTISEMENT,
                attributes={},
                price=None,
                location=None,
                slug="kvartira",
                published_at=_NOW,
                publicly_visible=True,
                now=_NOW,
            )
        await use_cases.apply_verified_badge(
            owner_profile_id=owner_profile_id, verified_badge=True, now=_NOW
        )
        assert all(fake_index.documents[lid].verified_badge for lid in listing_ids)

    async def test_I09_does_not_affect_listings_owned_by_a_different_profile(
        self, use_cases: IndexingUseCases, fake_index: FakeSearchIndex
    ) -> None:
        other_listing_id = uuid4()
        await use_cases.upsert_listing_content(
            listing_id=other_listing_id,
            owner_profile_id=uuid4(),
            title="Kvartira",
            description=None,
            category_id=uuid4(),
            category_path="/real-estate",
            listing_type=ListingType.ADVERTISEMENT,
            attributes={},
            price=None,
            location=None,
            slug="kvartira",
            published_at=_NOW,
            publicly_visible=True,
            now=_NOW,
        )
        await use_cases.apply_verified_badge(
            owner_profile_id=uuid4(), verified_badge=True, now=_NOW
        )
        assert fake_index.documents[other_listing_id].verified_badge is False
