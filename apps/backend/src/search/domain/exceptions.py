"""search -- typed domain exceptions, one per invariant violated (Playbook Sec 6). Mirrors
`catalog.domain.exceptions`'s style."""

from __future__ import annotations


class SearchDomainError(Exception):
    """Base for every typed exception raised by search's domain/ layer."""


class InvalidPromotionCapError(SearchDomainError):
    """I-17 / `SearchConfiguration.promotion_page_cap`'s own `CHECK (promotion_page_cap >= 0)`
    (Physical DB Design). Should be unreachable in practice -- configuration's own gate already
    enforces this at publish time -- but `apply_promotion_cap` guards against a negative value
    defensively rather than silently producing nonsense output (Playbook Sec 6: "fail closed on
    missing configuration")."""

    def __init__(self, cap: int) -> None:
        self.cap = cap
        super().__init__(f"promotion_page_cap must be >= 0, got {cap}")
