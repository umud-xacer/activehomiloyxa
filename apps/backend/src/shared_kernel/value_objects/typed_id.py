"""Strongly-typed identifier value objects -- shared kernel (DDD Sec 5.14; Database Architecture
& Logical Data Model Sec 10 "Identifier Strategy": "Internal ID ... wrapped in the strongly-typed
identifier VOs of the shared kernel (UserId, ListingId, ...). Never carries business meaning;
never reused.").

Centralising these in the shared kernel (rather than in the owning module's own domain/) is not
a style choice: a typed id must be nameable and constructible by every module that holds a
cross-context reference to the aggregate it identifies (e.g. `catalog.Listing.owner_user_id`
needs `UserId` without importing `identity.domain`), and the shared kernel is the only package
every module may import (SAD Sec 8.1).

`TypedId` wraps a bare UUID with a real, distinct runtime type per concept -- not a
`typing.NewType`, which only affects static analysis and provides no construction-time
validation or runtime identity of its own (the checklist here requires both: "validates its
invariants on construction, raising typed exceptions on invalid input" and testable
"equality/hashing behaviour"). It carries no business meaning and no reference to what the id
identifies beyond its own type name -- that is the module owning the aggregate's job, not the
shared kernel's.

Only the two ids the Database Architecture document names by example (`UserId`, `ListingId`)
are defined here; other concepts add their own `TypedId` subclass here when a later task's
domain/application code first needs one to name an aggregate it doesn't own -- inventing the
full roster now, before those aggregates exist, would be exactly the "module-specific type" this
task's scope excludes.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TypedId(BaseModel):
    """Base for a strongly-typed identifier. Every concrete subclass is a distinct runtime type
    -- `UserId(value=x) != ListingId(value=x)` even for the same underlying UUID -- so a value of
    the wrong kind cannot be passed where another is expected, neither at the type-checker level
    nor at runtime. Constructed by keyword (`UserId(value=some_uuid)`), not positionally: a
    custom positional `__init__` fights the pydantic mypy plugin's own synthesized-`__init__`
    checking, and keyword construction is unambiguous anyway."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: UUID

    def __str__(self) -> str:
        return str(self.value)


class UserId(TypedId):
    """Identifies a `UserAccount` (BC-01)."""


class ListingId(TypedId):
    """Identifies a `Listing` (BC-03)."""


class BusinessProfileId(TypedId):
    """Identifies a `BusinessProfile` (BC-02). Named here, ahead of BC-02's own implementation,
    because BC-01's `Session.acting_context` and `UserAccount.owned_profile_ids` (DDD Sec 5.1,
    FR-USER-002) must reference the acting/owned profile by id without importing
    `profiles.domain` -- exactly the "a later task's domain/application code first needs one to
    name an aggregate it doesn't own" case this module's docstring reserves."""


class MediaAssetId(TypedId):
    """Identifies a `MediaAsset` (BC-06). Named here for the same reason as `BusinessProfileId`:
    DDD Sec 6 X-06 documents that Catalog/Profiles/Ad-Serving "hold `MediaAssetRef` only" (a
    future task's `Listing`/`BusinessProfile`/`BannerCreative` attachment row references a
    `MediaAsset` by id without importing `media.domain`), and the Physical DB Sec 2 xref columns
    (`listing_media.media_asset_id`, `business_profile_media.media_asset_id`, ...) are typed
    accordingly."""
