"""`search.domain.search_document.ListingSearchDocument` -- `.project()` (fresh construction) and
the `with_*` re-projection methods (content/visibility/promotion/verified-badge), each scoped to
touch only the fields its own producing event stream owns."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from search.domain import ListingType, PromotionKind, PromotionMarker
from search.domain.search_document import ListingSearchDocument

_NOW = datetime(2026, 7, 12, tzinfo=UTC)


def _document(**overrides: object) -> ListingSearchDocument:
    kwargs: dict[str, object] = {
        "listing_id": uuid4(),
        "owner_profile_id": uuid4(),
        "title": "Kvartira sotiladi",
        "description": "3-xonali kvartira",
        "category_id": uuid4(),
        "category_path": "/real-estate/apartments",
        "listing_type": ListingType.ADVERTISEMENT,
        "attributes": {"rooms": "3"},
        "price": None,
        "location": None,
        "verified_badge": False,
        "publicly_visible": True,
        "slug": "kvartira-sotiladi",
        "published_at": _NOW,
        "updated_at": _NOW,
    }
    kwargs.update(overrides)
    return ListingSearchDocument.project(**kwargs)  # type: ignore[arg-type]


class TestProject:
    def test_I01_computes_cross_script_shadow_fields_from_the_title(self) -> None:
        document = _document(title="Kvartira")
        assert document.title_normalized_latin == "kvartira"
        assert document.title_normalized_cyrillic == "квартира"

    def test_I02_starts_with_no_promotion_and_a_caller_supplied_verified_badge(self) -> None:
        document = _document(verified_badge=True)
        assert document.promotion is None
        assert document.verified_badge is True


class TestWithContent:
    def test_I03_recomputes_shadow_fields_when_the_title_changes(self) -> None:
        document = _document(title="Kvartira")
        updated = document.with_content(
            title="Avtomobil",
            description=document.description,
            category_id=document.category_id,
            category_path=document.category_path,
            attributes=document.attributes,
            price=document.price,
            location=document.location,
            publicly_visible=document.publicly_visible,
            updated_at=_NOW,
        )
        assert updated.title_normalized_latin == "avtomobil"
        assert updated.title_normalized_cyrillic == "автомобил"

    def test_I04_leaves_promotion_and_verified_badge_untouched(self) -> None:
        document = _document(verified_badge=True).with_promotion(
            promotion=PromotionMarker(
                kind=PromotionKind.PREMIUM, valid_until=None, entitlement_id=uuid4()
            ),
            updated_at=_NOW,
        )
        updated = document.with_content(
            title="New title",
            description=None,
            category_id=document.category_id,
            category_path=document.category_path,
            attributes={},
            price=None,
            location=None,
            publicly_visible=True,
            updated_at=_NOW,
        )
        assert updated.promotion == document.promotion
        assert updated.verified_badge is True


class TestWithVisibility:
    def test_I05_changes_only_publicly_visible_and_updated_at(self) -> None:
        document = _document(publicly_visible=True)
        updated = document.with_visibility(publicly_visible=False, updated_at=_NOW)
        assert updated.publicly_visible is False
        assert updated.title == document.title
        assert updated.category_id == document.category_id


class TestWithPromotion:
    def test_I06_sets_the_promotion_marker(self) -> None:
        document = _document()
        marker = PromotionMarker(
            kind=PromotionKind.FEATURED, valid_until=None, entitlement_id=uuid4()
        )
        updated = document.with_promotion(promotion=marker, updated_at=_NOW)
        assert updated.promotion == marker

    def test_I07_clears_the_promotion_marker(self) -> None:
        document = _document().with_promotion(
            promotion=PromotionMarker(
                kind=PromotionKind.TOP_PLACEMENT, valid_until=None, entitlement_id=uuid4()
            ),
            updated_at=_NOW,
        )
        cleared = document.with_promotion(promotion=None, updated_at=_NOW)
        assert cleared.promotion is None


class TestWithVerifiedBadge:
    def test_I08_toggles_the_verified_badge_without_touching_other_fields(self) -> None:
        document = _document(verified_badge=False)
        updated = document.with_verified_badge(verified_badge=True, updated_at=_NOW)
        assert updated.verified_badge is True
        assert updated.title == document.title
