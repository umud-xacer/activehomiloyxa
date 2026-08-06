"""Unit tests for `MetricKey`/`ClosedVocabularyPolicy` (DDD Sec 5.13, DEC-06/BRULE-20/I-23).

`test_closed_vocabulary_accepts_exactly_the_eight_approved_keys` is this module's SIGNATURE
test: it enumerates the eight approved keys explicitly, so a future addition to `MetricKey`
breaks it deliberately (per the P-15 task charter's own instruction).
"""

from __future__ import annotations

import pytest

from analytics.domain import ClosedVocabularyPolicy, MetricKey, UnknownMetricKeyError

_APPROVED_KEYS = {
    "LISTING_VIEWED",
    "CONTACT_BUTTON_CLICKED",
    "PHONE_REVEALED",
    "CHAT_INITIATED",
    "FAVORITE_ADDED",
    "PREMIUM_LISTING_STAT",
    "BANNER_IMPRESSION_RECORDED",
    "BANNER_CLICK_RECORDED",
}


def test_closed_vocabulary_accepts_exactly_the_eight_approved_keys() -> None:
    """# enforces I-23/BRULE-20/DEC-06. Verified against DDD Sec 5.13's own literal list --
    exactly these eight, no others."""
    assert {member.value for member in MetricKey} == _APPROVED_KEYS
    assert len(_APPROVED_KEYS) == 8
    for key in _APPROVED_KEYS:
        assert ClosedVocabularyPolicy.validate(key) is MetricKey(key)


@pytest.mark.parametrize(
    "bad_key",
    [
        "OTHER",
        "listing_viewed",  # wrong case
        "LISTING_VIEW",  # near-miss
        "",
        "AD_CLICKED",
        "PAGE_VIEW",
    ],
)
def test_closed_vocabulary_rejects_anything_outside_the_eight_keys(bad_key: str) -> None:
    """THE module's signature test (P-15 task charter): a metric key outside the closed set is
    REJECTED with the typed exception -- never stored, never silently ignored, never bucketed
    into an "other" category (BRULE-20)."""
    with pytest.raises(UnknownMetricKeyError) as exc_info:
        ClosedVocabularyPolicy.validate(bad_key)
    assert exc_info.value.metric_key == bad_key
