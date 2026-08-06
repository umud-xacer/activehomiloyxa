"""TaxonomyService pure functions (I-03: "retiring/moving a Category must not orphan
listings")."""

from __future__ import annotations

from configuration.domain.taxonomy import creates_cycle, would_orphan_listings


def test_creates_cycle_true_when_code_is_its_own_ancestor() -> None:
    assert creates_cycle("housing", frozenset({"root", "housing"})) is True


def test_creates_cycle_false_when_code_absent_from_ancestor_chain() -> None:
    assert creates_cycle("housing", frozenset({"root", "commercial"})) is False


def test_I03_retiring_category_with_bound_listings_orphans_them() -> None:
    assert would_orphan_listings("RETIRED", True) is True


def test_I03_retiring_category_without_bound_listings_is_safe() -> None:
    assert would_orphan_listings("RETIRED", False) is False


def test_I03_non_retiring_status_never_orphans_regardless_of_listings() -> None:
    assert would_orphan_listings("ACTIVE", True) is False
