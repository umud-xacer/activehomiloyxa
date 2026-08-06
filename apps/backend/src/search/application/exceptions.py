"""search/application -- exceptions for facts the domain layer cannot know (I/O failures,
missing configuration). Mirrors `catalog.application.exceptions`'s style."""

from __future__ import annotations


class SearchApplicationError(Exception):
    """Base for every typed exception raised by search's application/ layer."""


class SearchIndexUnavailableError(SearchApplicationError):
    """Raised by `SearchIndexPort` when OpenSearch cannot be reached -- the signal
    `SearchUseCases` uses to switch to `FallbackIndexPort` (`DegradationPolicy [P]`, NFR-REL-002).
    Never raised by the fallback path itself; if the fallback also fails, that is a genuine 503,
    not a further degradation (there is no third tier)."""


class MalformedEventPayloadError(SearchApplicationError):
    """A content-bearing event (`ListingPublished`/`ListingEdited`) arrived without the fields
    `ListingSearchDocument` needs (title/category/slug/...). Raised rather than silently
    skipping: catalog's own currently-shipped `_listing_payload()` helper (Task P-07) sends only
    `listingId`/`ownerUserId`/`categoryId`/`lifecycleState`/`isFlagged`/`expiresAt`/`reason` --
    NOT the full content DB Architecture Sec 3.5/12 documents `ListingSearchDocument` as being
    "rebuilt from Catalog events" -- see `search/README.md` "Known gaps" for the full trace and
    the follow-up fix this raises attention to. Raising here (rather than a silent no-op) makes
    the gap visible via the outbox dispatcher's own retry/DEAD-letter machinery instead of
    producing a permanently-empty index with no signal anywhere that anything is wrong."""

    def __init__(self, event_type: str, missing_field: str) -> None:
        self.event_type = event_type
        self.missing_field = missing_field
        super().__init__(f"{event_type} payload is missing required field {missing_field!r}")


class NoSearchConfigurationPublishedError(SearchApplicationError):
    """No `SearchConfiguration` snapshot has ever been published for the requested scope
    (global or category). Fails closed (Playbook Sec 6): facets/sorts/the promotion cap all
    default to empty/zero rather than a hardcoded guess -- DEC-21 forbids inventing configuration
    data, even as a fallback default."""

    def __init__(self, category_id: object) -> None:
        self.category_id = category_id
        super().__init__(f"no published SearchConfiguration snapshot for scope {category_id!r}")
