"""`search.domain.ranking.apply_promotion_cap` -- I-17, BC-05's sole invariant: "Promoted search
results are always labelled and never exceed the configured per-page cap." Never re-orders;
only enforces the cap, dropping surplus promoted candidates from their own position (never
displacing an organic result beyond what the rules allow)."""

from __future__ import annotations

import pytest

from search.domain.exceptions import InvalidPromotionCapError
from search.domain.ranking import RankedCandidate, apply_promotion_cap


def _candidates(*promoted_flags: bool) -> list[RankedCandidate]:
    return [
        RankedCandidate(listing_id=index, is_promoted=flag)
        for index, flag in enumerate(promoted_flags)
    ]


class TestApplyPromotionCap:
    def test_I01_keeps_every_organic_candidate_regardless_of_cap(self) -> None:
        candidates = _candidates(False, False, False)
        result = apply_promotion_cap(candidates, cap=0)
        assert result == candidates

    def test_I02_drops_all_promoted_candidates_when_cap_is_zero(self) -> None:
        candidates = _candidates(True, False, True, False)
        result = apply_promotion_cap(candidates, cap=0)
        assert [c.is_promoted for c in result] == [False, False]

    def test_I03_keeps_promoted_candidates_up_to_the_cap_in_original_relative_order(self) -> None:
        candidates = _candidates(True, True, True)
        result = apply_promotion_cap(candidates, cap=2)
        assert result == candidates[:2]

    def test_I04_never_bumps_a_dropped_promoted_candidate_to_a_different_slot(self) -> None:
        # promoted at index 0,2,4; organic at 1,3 -- cap=1 keeps only the FIRST promoted one,
        # and every organic candidate remains at its own natural position (never displaced to
        # "fill" the gap left by a dropped promoted candidate).
        candidates = _candidates(True, False, True, False, True)
        result = apply_promotion_cap(candidates, cap=1)
        assert result == [candidates[0], candidates[1], candidates[3]]

    def test_I05_never_removes_an_organic_candidate(self) -> None:
        candidates = _candidates(True, True, True, True, True, False)
        result = apply_promotion_cap(candidates, cap=0)
        assert candidates[-1] in result
        assert len([c for c in result if not c.is_promoted]) == 1

    def test_I06_cap_larger_than_promoted_count_keeps_every_candidate(self) -> None:
        candidates = _candidates(True, False, True)
        result = apply_promotion_cap(candidates, cap=100)
        assert result == candidates

    def test_I07_empty_input_returns_empty_output(self) -> None:
        assert apply_promotion_cap([], cap=5) == []

    def test_I08_negative_cap_raises_invalid_promotion_cap_error(self) -> None:
        with pytest.raises(InvalidPromotionCapError):
            apply_promotion_cap(_candidates(True), cap=-1)

    def test_I09_does_not_mutate_the_input_list(self) -> None:
        candidates = _candidates(True, True)
        original = list(candidates)
        apply_promotion_cap(candidates, cap=0)
        assert candidates == original
