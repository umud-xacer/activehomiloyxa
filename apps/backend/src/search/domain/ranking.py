"""search -- `RankingService [P]`/`PromotionCapAndLabelPolicy [P mechanism, C value]` (DDD Sec
5.5; DEC-12: "Ranking blends relevance + recency + capped, labelled promotion boost sourced from
Billing"; I-17, BC-05's sole invariant: "Promoted search results are always labelled and never
exceed the configured per-page cap"). The relevance/recency BLEND itself (BM25 + boosts) is
engine-specific query construction and lives in `infrastructure/opensearch_index.py` (OpenSearch
query DSL) or the fallback adapter's own `ORDER BY` -- not portable domain logic. What IS portable,
pure, and carries the named invariant is the CAP: given an already-ranked sequence of candidates,
never let more than `cap` promoted ones survive onto one page. This is `apply_promotion_cap`,
exercised identically regardless of which engine produced the ranking.

No numeric cap is hardcoded anywhere in this module -- `cap` is always a parameter, sourced at
the call site from `SearchConfiguration.promotion_page_cap` (DEC-21: configuration is data). No
approved document specifies a default/example number (confirmed absent from SRS, Domain Model,
Baseline, Configuration Framework, and Physical DB Design after an exhaustive search) -- the only
documented constraint is `promotion_page_cap >= 0`, enforced by the config's own CHECK, not here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from search.domain.exceptions import InvalidPromotionCapError


class _Rankable(Protocol):
    @property
    def is_promoted(self) -> bool: ...


def apply_promotion_cap[T: _Rankable](ranked_candidates: list[T], *, cap: int) -> list[T]:
    """`ranked_candidates` is already in final relevance/recency/promotion-blended order (from
    OpenSearch scoring or the DB fallback's own ordering) -- this function only ENFORCES I-17,
    it never re-orders. Walks the list once, keeping every non-promoted candidate and at most
    `cap` promoted ones (in their existing relative order); once the promoted budget is spent,
    subsequent promoted candidates are dropped from that position entirely -- never bumped to a
    different slot, never used to displace an organic result beyond their own natural rank. This
    is what keeps an organic listing from being "entirely displaced beyond what the rules allow"
    (P-08's own validation checklist): dropping a promoted candidate can only ever reveal the
    organic candidate that was already next in line, never remove one."""
    if cap < 0:
        raise InvalidPromotionCapError(cap)
    kept: list[T] = []
    promoted_count = 0
    for candidate in ranked_candidates:
        if candidate.is_promoted:
            if promoted_count >= cap:
                continue
            promoted_count += 1
        kept.append(candidate)
    return kept


@dataclass(frozen=True)
class RankedCandidate:
    """A minimal, engine-agnostic wrapper satisfying `_Rankable` -- callers that already have a
    richer hit object (e.g. an OpenSearch/fallback row) can either implement `is_promoted`
    themselves or wrap it in this before calling `apply_promotion_cap`."""

    listing_id: object
    is_promoted: bool
