"""TaxonomyService (DDD Sec 5.4 domain service; I-03: "retiring/moving a Category must not
orphan listings; TaxonomyService requires a remap or blocks the change"). Pure functions over
pre-fetched facts -- the calling use case fetches the ancestor chain and listing-binding flag via
repository/lookup ports (Clean Architecture rule 1) and passes them in.
"""

from __future__ import annotations


def creates_cycle(category_code: str, ancestor_codes_of_proposed_parent: frozenset[str]) -> bool:
    """A move/create would make `category_code` its own ancestor via the proposed parent."""
    return category_code in ancestor_codes_of_proposed_parent


def would_orphan_listings(tree_status: str, has_bound_listings: bool) -> bool:
    """I-03: retiring a category that still has listings bound to it, without an explicit
    remap, orphans those listings."""
    return tree_status == "RETIRED" and has_bound_listings
