"""catalog/application -- ports (Task P-07). Abstract surface only (typing.Protocol);
`infrastructure/` implements every one of these, never the reverse (Clean Architecture rule 4).

Every cross-module read is shaped as catalog's *own* narrow Protocol/dataclass here -- never a
`configuration.interfaces`/`media.interfaces`/`identity.interfaces` type imported directly into
this file -- exactly the discipline `identity.application.ports.RoleDefinitionReaderPort`/
`PlatformSettingsReaderPort` already set in P-05 (that module's own docstring: "Provider SDK
types never appear here"; the same reasoning extends to *other-module* DTOs, which are just as
foreign to this layer). The concrete adapter bridging to the other module's `interfaces/` package
lives in `catalog/infrastructure/`, wired only at the composition root
(`cross-module-catalog`, tools/importlinter.cfg)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol
from uuid import UUID

from catalog.domain import Favorite, FieldValidatorSpec, Listing
from shared_kernel import BusinessProfileId, ListingId, UserId


class ListingRepository(Protocol):
    """One repository per aggregate (`Listing`, including its `ImageAttachment`/
    `LifecycleTransitionRecord` child entities -- Clean Architecture rule 2). Every finder here
    is intention-revealing (named for the use case it backs), never a generic query builder."""

    async def get_by_id(self, listing_id: ListingId) -> Listing | None: ...

    async def add(self, listing: Listing) -> None: ...

    async def save(self, listing: Listing) -> Listing:
        """Returns the persisted aggregate with its post-flush `lock_version`
        (`backbone.persistence.AggregateMixin`'s `version_id_col` bumps it on every `UPDATE`) --
        callers must use the returned value, not the one passed in, since `Listing` is immutable
        and the caller's own reference still carries the pre-flush version (OpenAPI `Listing.
        lockVersion`'s "echo it on update" only works if the *response* carries the new value).
        May raise `catalog.application.exceptions.StaleListingVersionError` if `version_id_col`
        detects a lost update within this request (defense in depth) -- the primary
        echoed-lockVersion check runs earlier, in the use case, against the freshly loaded
        aggregate."""
        ...

    async def get_by_image_media_asset_id(self, media_asset_id: UUID) -> Listing | None:
        """Backs the media asset-status projection (X-06): at most one listing holds a given
        media asset attached at a time (I-04's own attach/detach discipline), so this returns a
        single result, not a list."""
        ...

    async def list_by_owner(
        self,
        owner_user_id: UserId,
        *,
        state: str | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[Listing], str | None]:
        """Backs `listMyListings`. Returns `(listings, next_cursor)`; every lifecycle state is
        visible to the owner, unlike `list_public`."""
        ...

    async def list_by_owner_profile(
        self,
        owner_profile_id: BusinessProfileId,
        *,
        state: str | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[Listing], str | None]:
        """Backs the subscription-visibility projection (`ListingUseCases.
        suspend_all_by_owner_profile`/`reactivate_all_by_owner_profile`): every listing created
        under this business profile's acting context, regardless of which user account acted
        (mirrors `list_by_owner`'s shape exactly, keyed by `owner_profile_id` instead of
        `owner_user_id` -- the two are independent columns on the same row, DDD Sec 5.3)."""
        ...

    async def list_public(
        self,
        *,
        category_id: UUID | None,
        listing_type: str | None,
        cursor: str | None,
        limit: int,
        now: datetime,
    ) -> tuple[list[Listing], str | None]:
        """Backs `listListings` (BC-05/search indexing is explicitly out of this task's scope --
        this is catalog's own fallback query surface, not a search engine). Only rows for which
        `Listing.is_publicly_visible(now=now)` is `True` (I-06, the single authoritative rule) are
        returned; the repository pushes the same three predicates down to SQL rather than
        filtering in Python, but the *rule* itself is owned by the domain method, not re-derived
        here."""
        ...

    async def list_expiring(self, *, now: datetime, limit: int) -> list[Listing]:
        """Backs the expiry sweep worker: `lifecycle_state IN (PUBLISHED, EDITED)`,
        `expires_at <= now`, and the most recent transition is not already `EXPIRE` (idempotency
        is re-checked by `Listing.record_expiry` itself, but the repository still excludes
        already-swept rows so a large backlog does not get re-fetched every poll)."""
        ...

    async def count_active_by_owner_profile(self, owner_profile_id: BusinessProfileId) -> int:
        """Backs `QuotaEnforcementService` (I-08): the count of this business profile's listings
        not in a terminal `DELETED` state -- the quota-relevant "active" count against
        `SubscriptionSnapshot.quota_document["max_active_listings"]`."""
        ...

    async def find_recent_by_owner_category(
        self,
        *,
        owner_user_id: UserId,
        category_id: UUID,
        exclude_listing_id: ListingId | None,
        limit: int,
    ) -> list[Listing]:
        """Backs `DuplicateDetectionService` (FR-ADV-009): candidate scope is "same owner, same
        category", scoped further by the pure title comparator in
        `catalog.domain.policies.normalize_title_for_duplicate_matching`."""
        ...


class FavoriteRepository(Protocol):
    """A distinct repository for the distinct `Favorite` aggregate root (DDD Sec 5.3: "Separate
    from Listing so favoriting never contends with listing writes")."""

    async def get(self, *, user_id: UserId, listing_id: ListingId) -> Favorite | None: ...

    async def add(self, favorite: Favorite) -> None: ...

    async def delete(self, *, user_id: UserId, listing_id: ListingId) -> None: ...

    async def list_for_user(
        self, user_id: UserId, *, cursor: str | None, limit: int
    ) -> tuple[list[Favorite], str | None]: ...

    async def count_for_listing(self, listing_id: ListingId) -> int:
        """Backs `getListingStatistics`'s `favorites` count -- catalog's own data, unlike
        `views`/`contactClicks`/`phoneReveals`/`chatsInitiated` (Analytics-owned, BC-13, outside
        catalog's declared dependency set; see catalog/README.md "Known gaps")."""
        ...


@dataclass(frozen=True)
class CategorySnapshot:
    """catalog's own narrow read shape for a configured Category (I-01/I-02) -- not
    `configuration.interfaces.dto.Category`."""

    id: UUID
    path: str
    status: Literal["ACTIVE", "RETIRED"]
    form_definition_head_id: UUID | None


@dataclass(frozen=True)
class FormBinding:
    """The category's currently-bound form (I-02), flattened into the closed six-`validator_type`
    vocabulary `catalog.domain.policies.validate_attribute_set` executes. Resolved fresh at
    `createListing` *and* at every `updateListing` (I-07's own "re-binds/re-validates against the
    current form version", `interfaces/dto.py::ListingUpdateRequest`) -- the listing then holds
    this binding fixed until its *next* edit, never drifting on its own as configuration
    publishes further versions in between (see `catalog.domain.listing.Listing`'s own field
    docstring)."""

    form_definition_id: UUID
    """The form-definition head id (`configuration` `ConfigurationHead.id` for entity_type
    "form-definition")."""
    form_definition_version_id: UUID
    specs: tuple[FieldValidatorSpec, ...]
    field_codes: frozenset[str] | None = None
    """Every field code the bound form actually declares (UNF-020) -- NOT derivable from
    `specs` alone, since a field with no configured validators produces zero `FieldValidatorSpec`
    entries but is still a legitimate attribute key. `validate_attribute_set` uses this to reject
    a key the form's own author never declared, rather than silently persisting it.
    `ConfigurationCategoryFormAdapter` (the only real production implementation) always supplies
    it; `None` (the default) exists so a test fake can under-specify a binding without opting
    into the unknown-field check."""


class CategoryFormPort(Protocol):
    """Reads Category + bound FormDefinition snapshots from `configuration` (I-01/I-02/I-07).
    The concrete adapter calls `configuration.interfaces.ports.ConfigurationPort.get_category`/
    `get_category_form` only -- never `configuration.domain`/`application`/`infrastructure`
    (`cross-module-catalog`)."""

    async def get_category(self, category_id: UUID) -> CategorySnapshot | None: ...

    async def get_current_form_binding(self, category_id: UUID) -> FormBinding | None:
        """`None` if the category has no published bound form
        (`catalog.application.exceptions.CategoryFormUnavailableError` is raised by the caller,
        not this port)."""
        ...


@dataclass(frozen=True)
class CatalogPlatformSettings:
    """The subset of `platform-settings-global` (configuration, seeded in P-04) catalog's own
    policies read at runtime (DEC-21: never hardcode a configurable value)."""

    default_expiry_days: int
    """FR-ADV-007's configurable renewal/expiry period (`SETTINGS_SCHEMA["listing.default_expiry_
    days"]`, `configuration.domain.whitelist`)."""


class PlatformSettingsReaderPort(Protocol):
    async def get_catalog_settings(self) -> CatalogPlatformSettings: ...


@dataclass(frozen=True)
class MediaAssetSnapshot:
    """catalog's own narrow read shape for a `MediaAsset` (X-06: "Catalog ... hold `MediaAssetRef`
    only") -- not `media.interfaces.dto.MediaAsset`. No uploader/owner field: `media.interfaces.
    dto.MediaAsset` (the only shape `MediaIntakePort.get_media` returns) does not carry one --
    `getMedia`'s own docstring makes the omission deliberate ("no ownership check ... delivery
    metadata is meant to be readable by whatever page embeds the image"), so there is no
    sanctioned way for catalog to verify the caller uploaded a given asset at attach time."""

    id: UUID
    scan_status: Literal["PENDING", "CLEAN", "QUARANTINED"]
    thumbnail_url: str | None = None
    """Delivery URL of the asset's THUMBNAIL variant, or `None` until processing completes.

    Read-through only: catalog forwards this on `ListingPublished`/`ListingEdited` so search can
    populate `SearchHit.thumbnailUrl`, and never persists it. X-06's "Owners hold `MediaAssetRef`
    only" governs stored aggregate state -- `ImageAttachment` still holds nothing but the ref --
    and search cannot rebuild the URL from a ref on its own, because the variant's extension
    follows the source image's format (`thumbnail.png` vs `thumbnail.jpg`)."""


class MediaAssetReaderPort(Protocol):
    """The concrete adapter calls `media.interfaces.ports.MediaIntakePort.get_media` only
    (`cross-module-catalog`)."""

    async def get_media_asset(self, media_asset_id: UUID) -> MediaAssetSnapshot | None: ...


@dataclass(frozen=True)
class SubscriptionSnapshot:
    """A locally projected read model of a billing entitlement (I-08: "catalog must NOT import
    billing" -- this row is written only by `apply_entitlement_projection`'s idempotent consumer
    of billing's *outbox events*, never by a synchronous call into a billing module, which does
    not exist as of this task). Physical DB `catalog.subscription_projection`: keyed by
    `owner_profile_id` alone -- a personal (non-business-profile) owner, or a business profile
    that billing has never issued an entitlement for, simply has no row here, which
    `QuotaEnforcementService` treats as unlimited (see its own docstring)."""

    owner_profile_id: BusinessProfileId
    entitlement_id: UUID
    product_definition_id: UUID | None
    quota_document: dict[str, Any]
    """No shape is specified by any approved document (Physical DB Sec 5.2: "JSONB, no specified
    shape") -- `QuotaEnforcementService` reads only the one key it needs
    (`"max_active_listings"`), tolerating any other shape leniently."""
    valid_until: datetime | None
    source_event_id: UUID
    """The billing event id this snapshot was last written from -- the idempotency key
    `apply_entitlement_projection` upserts on (I-08's "idempotent... projection")."""


class SubscriptionSnapshotRepository(Protocol):
    async def get_for_profile(
        self, owner_profile_id: BusinessProfileId
    ) -> SubscriptionSnapshot | None: ...

    async def upsert(self, snapshot: SubscriptionSnapshot) -> None: ...


class CreditBalancePort(Protocol):
    """Listing paywall Phase 4 (2026-08-23): the narrow slice of billing's
    `LISTING_CREDIT_BALANCE` entitlements catalog needs at listing-creation time -- catalog never
    imports billing (AIR-10/`cross-module-catalog`); the composition root bridges this in-process
    (mirrors `identity.infrastructure.configuration_adapter`'s own `_ConfigReader` shape /
    `composition_root._ConfigurationPortBridge`), opening billing's own session/transaction,
    independent of and committed BEFORE `ListingUseCases.create_listing`'s own -- a mid-failure
    after a successful consume loses a credit rather than granting a free unpaid listing."""

    async def consume_one_listing_credit(self, *, owner_profile_id: BusinessProfileId) -> bool:
        """Attempts to spend one listing-publish credit from the profile's earliest-expiring
        active `LISTING_CREDIT_BALANCE` entitlement. Returns `True` if a credit was available and
        consumed (the caller should publish immediately, `requires_payment=False`), `False` if
        none was available (`requires_payment=True`)."""
        ...
