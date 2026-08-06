"""`search.infrastructure.event_projection` -- routing (`dispatch_search_event`), idempotency
(replay the same event twice -> same document, no double side effect, via `ProcessedEventRow`'s
`(event_id, handler)` ledger), and the `MalformedEventPayloadError` deferred-gap behaviour for
content-bearing events missing required fields. Uses `FakeIdempotentSession` (conftest.py) --
`idempotent_consume`'s own `INSERT ... ON CONFLICT` is Postgres-only, covered for real by the
(skip-without-Postgres) integration tier; this tier owns the routing/idempotency *contract*."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from search.application.exceptions import MalformedEventPayloadError
from search.application.indexing_use_cases import IndexingUseCases
from search.infrastructure.event_projection import dispatch_search_event
from shared_kernel import EventEnvelope

from .conftest import FakeFallbackIndex, FakeSearchIndex

_NOW = datetime(2026, 7, 12, tzinfo=UTC)


def _envelope(
    event_type: str, payload: dict[str, object], *, event_id: UUID | None = None
) -> EventEnvelope:
    return EventEnvelope(
        event_id=event_id or uuid4(),
        event_type=event_type,
        occurred_at=_NOW,
        aggregate_type="Listing",
        aggregate_id=uuid4(),
        payload=payload,
    )


def _content_payload(listing_id: object, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "listingId": str(listing_id),
        "title": "Kvartira",
        "categoryId": str(uuid4()),
        "categoryPath": "/real-estate",
        "listingType": "ADVERTISEMENT",
        "slug": "kvartira",
        "isPubliclyVisible": True,
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def use_cases(fake_index: FakeSearchIndex, fake_fallback: FakeFallbackIndex) -> IndexingUseCases:
    return IndexingUseCases(index=fake_index, fallback=fake_fallback)


class TestContentRouting:
    async def test_I01_listing_published_indexes_a_new_document(
        self,
        fake_session: AsyncSession,
        use_cases: IndexingUseCases,
        fake_index: FakeSearchIndex,
    ) -> None:
        listing_id = uuid4()
        envelope = _envelope("ListingPublished", _content_payload(listing_id))
        await dispatch_search_event(fake_session, envelope, use_cases)
        assert listing_id in fake_index.documents
        assert fake_index.documents[listing_id].title == "Kvartira"

    async def test_I02_listing_edited_re_projects_content(
        self,
        fake_session: AsyncSession,
        use_cases: IndexingUseCases,
        fake_index: FakeSearchIndex,
    ) -> None:
        listing_id = uuid4()
        published = _envelope("ListingPublished", _content_payload(listing_id))
        await dispatch_search_event(fake_session, published, use_cases)
        edited = _envelope("ListingEdited", _content_payload(listing_id, title="Kvartira (edited)"))
        await dispatch_search_event(fake_session, edited, use_cases)
        assert fake_index.documents[listing_id].title == "Kvartira (edited)"

    async def test_I03_missing_required_field_raises_malformed_event_payload_error(
        self, fake_session: AsyncSession, use_cases: IndexingUseCases
    ) -> None:
        payload = _content_payload(uuid4())
        del payload["title"]
        envelope = _envelope("ListingPublished", payload)
        with pytest.raises(MalformedEventPayloadError) as exc_info:
            await dispatch_search_event(fake_session, envelope, use_cases)
        assert exc_info.value.missing_field == "title"


class TestVisibilityRouting:
    @pytest.mark.parametrize(
        "event_type",
        [
            "ListingSuspended",
            "ListingArchived",
            "ListingDeleted",
            "ListingExpired",
            "ListingRenewed",
        ],
    )
    async def test_I04_visibility_events_never_raise_even_with_a_minimal_payload(
        self,
        fake_session: AsyncSession,
        use_cases: IndexingUseCases,
        fake_index: FakeSearchIndex,
        event_type: str,
    ) -> None:
        listing_id = uuid4()
        published = _envelope("ListingPublished", _content_payload(listing_id))
        await dispatch_search_event(fake_session, published, use_cases)
        envelope = _envelope(
            event_type, {"listingId": str(listing_id), "lifecycleState": "SUSPENDED"}
        )
        await dispatch_search_event(fake_session, envelope, use_cases)
        assert fake_index.documents[listing_id].publicly_visible is False


class TestEntitlementRouting:
    async def test_I05_entitlement_activated_applies_a_promotion_marker(
        self,
        fake_session: AsyncSession,
        use_cases: IndexingUseCases,
        fake_index: FakeSearchIndex,
    ) -> None:
        listing_id = uuid4()
        await dispatch_search_event(
            fake_session, _envelope("ListingPublished", _content_payload(listing_id)), use_cases
        )
        envelope = _envelope(
            "EntitlementActivated",
            {"listingId": str(listing_id), "kind": "PREMIUM", "entitlementId": str(uuid4())},
        )
        await dispatch_search_event(fake_session, envelope, use_cases)
        promotion = fake_index.documents[listing_id].promotion
        assert promotion is not None
        assert promotion.kind.value == "PREMIUM"

    @pytest.mark.parametrize("event_type", ["EntitlementExpired", "EntitlementRevoked"])
    async def test_I06_entitlement_cleared_removes_the_promotion_marker(
        self,
        fake_session: AsyncSession,
        use_cases: IndexingUseCases,
        fake_index: FakeSearchIndex,
        event_type: str,
    ) -> None:
        listing_id = uuid4()
        await dispatch_search_event(
            fake_session, _envelope("ListingPublished", _content_payload(listing_id)), use_cases
        )
        await dispatch_search_event(
            fake_session,
            _envelope(
                "EntitlementActivated",
                {"listingId": str(listing_id), "kind": "FEATURED", "entitlementId": str(uuid4())},
            ),
            use_cases,
        )
        await dispatch_search_event(
            fake_session, _envelope(event_type, {"listingId": str(listing_id)}), use_cases
        )
        assert fake_index.documents[listing_id].promotion is None


class TestVerifiedBadgeRouting:
    async def test_I07_business_verified_sets_the_badge_on_every_owned_listing(
        self,
        fake_session: AsyncSession,
        use_cases: IndexingUseCases,
        fake_index: FakeSearchIndex,
    ) -> None:
        owner_profile_id = uuid4()
        listing_id = uuid4()
        await dispatch_search_event(
            fake_session,
            _envelope(
                "ListingPublished",
                _content_payload(listing_id, ownerProfileId=str(owner_profile_id)),
            ),
            use_cases,
        )
        await dispatch_search_event(
            fake_session,
            _envelope("BusinessVerified", {"businessProfileId": str(owner_profile_id)}),
            use_cases,
        )
        assert fake_index.documents[listing_id].verified_badge is True

    @pytest.mark.parametrize("event_type", ["VerificationRejected", "VerifiedBadgeExpired"])
    async def test_I08_clears_the_badge(
        self,
        fake_session: AsyncSession,
        use_cases: IndexingUseCases,
        fake_index: FakeSearchIndex,
        event_type: str,
    ) -> None:
        owner_profile_id = uuid4()
        listing_id = uuid4()
        await dispatch_search_event(
            fake_session,
            _envelope(
                "ListingPublished",
                _content_payload(listing_id, ownerProfileId=str(owner_profile_id)),
            ),
            use_cases,
        )
        await dispatch_search_event(
            fake_session,
            _envelope("BusinessVerified", {"businessProfileId": str(owner_profile_id)}),
            use_cases,
        )
        await dispatch_search_event(
            fake_session,
            _envelope(event_type, {"businessProfileId": str(owner_profile_id)}),
            use_cases,
        )
        assert fake_index.documents[listing_id].verified_badge is False


class TestUnknownEventType:
    async def test_I09_an_undocumented_event_type_is_silently_ignored_not_an_error(
        self, fake_session: AsyncSession, use_cases: IndexingUseCases
    ) -> None:
        envelope = _envelope("FavoriteAdded", {"listingId": str(uuid4())})
        await dispatch_search_event(fake_session, envelope, use_cases)


class TestIdempotency:
    """Replay the SAME event twice -> the second delivery is a no-op (same document, no double
    side effect), keyed on `(event_id, handler)` via `ProcessedEventRow`."""

    async def test_I10_replaying_the_same_listing_published_event_is_a_no_op_the_second_time(
        self,
        fake_session: AsyncSession,
        use_cases: IndexingUseCases,
        fake_index: FakeSearchIndex,
    ) -> None:
        listing_id = uuid4()
        event_id = uuid4()
        envelope = _envelope("ListingPublished", _content_payload(listing_id), event_id=event_id)
        await dispatch_search_event(fake_session, envelope, use_cases)
        first_document = fake_index.documents[listing_id]

        # simulate redelivery: the exact same envelope, dispatched again.
        replay = _envelope("ListingPublished", _content_payload(listing_id), event_id=event_id)
        await dispatch_search_event(fake_session, replay, use_cases)

        assert fake_index.documents[listing_id] == first_document

    async def test_I11_a_genuinely_new_event_id_is_not_treated_as_a_replay(
        self,
        fake_session: AsyncSession,
        use_cases: IndexingUseCases,
        fake_index: FakeSearchIndex,
    ) -> None:
        listing_id = uuid4()
        await dispatch_search_event(
            fake_session, _envelope("ListingPublished", _content_payload(listing_id)), use_cases
        )
        edited = _envelope("ListingEdited", _content_payload(listing_id, title="New title"))
        await dispatch_search_event(fake_session, edited, use_cases)
        assert fake_index.documents[listing_id].title == "New title"

    async def test_I12_different_handlers_are_independent_ledger_keys(
        self,
        fake_session: AsyncSession,
        use_cases: IndexingUseCases,
        fake_index: FakeSearchIndex,
    ) -> None:
        # a listing-projection event and an entitlement-projection event never collide in the
        # ledger even if (hypothetically) they shared an event_id -- `handler` is part of the key.
        shared_event_id = uuid4()
        listing_id = uuid4()
        await dispatch_search_event(
            fake_session,
            _envelope("ListingPublished", _content_payload(listing_id), event_id=shared_event_id),
            use_cases,
        )
        await dispatch_search_event(
            fake_session,
            _envelope(
                "EntitlementActivated",
                {"listingId": str(listing_id), "kind": "PREMIUM", "entitlementId": str(uuid4())},
                event_id=shared_event_id,
            ),
            use_cases,
        )
        assert fake_index.documents[listing_id].promotion is not None
