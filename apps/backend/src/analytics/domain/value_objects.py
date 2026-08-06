"""analytics/domain -- value objects. `MetricKey` is the closed v1 vocabulary itself (DDD Sec
5.13, DEC-06/BRULE-20/I-23); `ClosedVocabularyPolicy` is the first-class domain policy object
that guards it -- not a validation afterthought (P-15 task charter).
"""

from __future__ import annotations

from enum import StrEnum

from analytics.domain.exceptions import UnknownMetricKeyError


class MetricKey(StrEnum):
    """The closed v1 metric vocabulary -- EXACTLY these eight keys, no others (DDD Sec 5.13,
    verified against the Domain Model's own literal list). Values are the Physical Database
    Design's own `metric_key` CHECK-constraint literals (SCREAMING_SNAKE_CASE, the persisted
    form); each member's docstring names the PascalCase domain-event name it is projected from
    (DDD Sec 6 event catalogue naming)."""

    LISTING_VIEWED = "LISTING_VIEWED"
    """From `ListingViewed` (catalog, ADR-0005)."""
    CONTACT_BUTTON_CLICKED = "CONTACT_BUTTON_CLICKED"
    """From `ContactButtonClicked` (catalog, ADR-0005)."""
    PHONE_REVEALED = "PHONE_REVEALED"
    """From `PhoneRevealed` (messaging)."""
    CHAT_INITIATED = "CHAT_INITIATED"
    """From `ChatInitiated` (messaging)."""
    FAVORITE_ADDED = "FAVORITE_ADDED"
    """From `FavoriteAdded` (catalog)."""
    PREMIUM_LISTING_STAT = "PREMIUM_LISTING_STAT"
    """From `PremiumListingStat` (catalog, ADR-0005)."""
    BANNER_IMPRESSION_RECORDED = "BANNER_IMPRESSION_RECORDED"
    """From `BannerImpressionRecorded` (ads)."""
    BANNER_CLICK_RECORDED = "BANNER_CLICK_RECORDED"
    """From `BannerClickRecorded` (ads)."""


class ClosedVocabularyPolicy:
    """# enforces I-23/BRULE-20/DEC-06. The guard against metric-vocabulary scope creep -- a
    first-class domain object, not a field validator: every path that could ever construct a
    `MetricEvent` (the real ingestion use case, tests, a future admin tool) must pass through
    `validate`, and `MetricEvent.create` calls it internally rather than relying on callers to
    remember to."""

    @staticmethod
    def validate(metric_key: str) -> MetricKey:
        try:
            return MetricKey(metric_key)
        except ValueError as exc:
            raise UnknownMetricKeyError(metric_key) from exc
