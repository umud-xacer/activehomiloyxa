"""catalog -- the `Listing` aggregate (DDD Sec 5.3 `AR: Listing [P]`). Persistence-ignorant,
mirrors `identity.domain.user_account`/`media.domain.media_asset`'s style: frozen dataclass,
every state transition returns a new instance via `dataclasses.replace`, guarded by a typed
exception raised before the replace. `ImageAttachment` and `LifecycleTransitionRecord` are child
entities inside this aggregate's boundary (one repository, one unit of work, Clean Architecture
rule 2).

I-05's "only legal transitions, every transition recorded" is enforced procedurally: every
lifecycle-changing method appends exactly one `LifecycleTransitionRecord` via `_record` before
returning, and every method's own guard clause is the sole authority on which `LifecycleState`s
it accepts (`ListingLifecycleService [P]`'s "sole authority for state transitions" from DDD Sec
5.3 -- realised as the aggregate's own methods, not a separate service class, since DDD Sec 5.3
also says "state transitions live inside domain objects guarded by their invariant" per this
task's own standing orders).

Attribute-set validation (the validation engine [P] executing configured rules [C], DB
Architecture Sec 14.3) deliberately does NOT happen inside this file: it needs the bound
FormDefinition version's field specs, which only `application/` has fetched (via
`configuration.interfaces`) by the time `create`/`edit_content` are called -- see
`policies.py::validate_attribute_set`, invoked by the use case *before* calling into this
aggregate, exactly like `media.domain.MediaAsset.initiate` validates size/type internally only
because that data needs no I/O to know, whereas the form spec here does.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any
from uuid import UUID

from catalog.domain.exceptions import (
    DuplicateImagePositionError,
    IllegalListingStateTransitionError,
    ImageAttachmentNotFoundError,
    ImageLimitExceededError,
    ListingAlreadyFlaggedError,
    ListingNotFlaggedError,
)
from catalog.domain.image_attachment import ImageAttachment
from catalog.domain.lifecycle_transition_record import LifecycleTransitionRecord
from catalog.domain.value_objects import (
    ImageStatus,
    LifecycleState,
    ListingType,
    PromotionKind,
    PromotionMarker,
    TransitionKind,
)
from shared_kernel import BusinessProfileId, GeoLocation, ListingId, Money, UserId

MAX_IMAGE_ATTACHMENTS = 10
"""I-04 / BRULE-06: "at most 10 image attachments"; the literal spec number."""

_VISIBLE_STATES = frozenset({LifecycleState.PUBLISHED, LifecycleState.EDITED})
"""I-06: "publicly visible only in Published/Edited states"."""


@dataclass(frozen=True)
class Listing:
    """`lock_version` matches `backbone.persistence.AggregateMixin`'s optimistic-locking column,
    echoed by callers on update (OpenAPI `Listing.lockVersion`'s own "echo it on update"
    docstring). `category_id`/`owner_user_id`/`owner_profile_id` are set once by `create` and
    never appear as a parameter on any other method on this class -- I-01's "fixed for life" is
    enforced by the type itself having no method that could touch them, not by a runtime check."""

    id: ListingId
    listing_type: ListingType
    owner_user_id: UserId
    owner_profile_id: BusinessProfileId | None
    category_id: UUID
    category_path: str
    form_definition_id: UUID
    form_definition_version_id: UUID
    """Bound at `create`, held fixed until the next `edit_content` call (I-07: "frozen per
    edit-cycle" -- a form version published by `configuration` in the meantime never
    retroactively invalidates or silently rebinds an untouched listing). `edit_content` itself
    *does* rebind to whatever version `application/` resolves as current at that moment
    (`interfaces/dto.py::ListingUpdateRequest`'s own "re-binds/re-validates against the current
    form version") -- re-validation is a deliberate, owner-triggered act, not passive drift."""
    title: str
    description: str | None
    attributes: dict[str, Any]
    """The AttributeSet (DM-02): one typed document, not an EAV table."""
    price: Money | None
    location: GeoLocation | None
    lifecycle_state: LifecycleState
    is_flagged: bool
    awaiting_payment: bool
    """Listing paywall (2026-08-23): `True` for a `DRAFT` listing whose publish is held pending
    payment (`ListingUseCases.create_listing(..., requires_payment=True)`) -- an orthogonal
    field, not a `LifecycleState` value (mirrors `is_flagged`'s own shape, not a new state: I-06's
    visibility rule already excludes every `DRAFT`, paid or not, so this carries no visibility
    logic of its own -- it exists purely so the owner/frontend can tell "an ordinary unfinished
    draft" apart from "a finished draft sitting behind the paywall"). Cleared by `publish()`
    unconditionally (the only method that ever moves a listing out of `DRAFT`), never set directly
    by any other transition."""
    expires_at: datetime | None
    published_at: datetime | None
    promotion: PromotionMarker | None
    slug: str
    images: tuple[ImageAttachment, ...]
    transitions: tuple[LifecycleTransitionRecord, ...]
    created_at: datetime
    updated_at: datetime
    lock_version: int = 1
    """`AggregateMixin`'s `version_id_col` generator always assigns `1` to a brand-new row on
    INSERT (SQLAlchemy calls it unconditionally, overriding whatever value the ORM object was
    constructed with -- see `sqlalchemy.orm.persistence`), never `0`; a freshly `create()`d
    `Listing` that has not yet round-tripped through the repository must default to the same
    value its first persisted read will report, or a `save()` immediately following `add()` (with
    no intervening reload) will look stale against its own just-inserted row."""

    # --- factory (FR-ADV-001) -----------------------------------------------------------------

    @staticmethod
    def create(
        *,
        listing_id: ListingId,
        record_id: UUID,
        listing_type: ListingType,
        owner_user_id: UserId,
        owner_profile_id: BusinessProfileId | None,
        category_id: UUID,
        category_path: str,
        form_definition_id: UUID,
        form_definition_version_id: UUID,
        title: str,
        description: str | None,
        attributes: dict[str, Any],
        price: Money | None,
        location: GeoLocation | None,
        slug: str,
        now: datetime,
    ) -> Listing:
        """Always produces a `DRAFT` (DDD Sec 5.3 `ListingFactory`: "stamps ownership from the
        acting profile"). Immediate publication (`ListingCreateRequest.publish=true`) is the
        application layer composing `create` then `publish` as two recorded transitions, not a
        third state -- `contracts/openapi.yaml`'s own CHECK constraint enumerates exactly seven
        `lifecycle_state` values, none of them a combined "created-and-published" state."""
        transition = LifecycleTransitionRecord(
            id=record_id,
            from_state=None,
            to_state=LifecycleState.DRAFT,
            transition_kind=TransitionKind.CREATE,
            actor_user_id=owner_user_id.value,
            reason=None,
            occurred_at=now,
        )
        return Listing(
            id=listing_id,
            listing_type=listing_type,
            owner_user_id=owner_user_id,
            owner_profile_id=owner_profile_id,
            category_id=category_id,
            category_path=category_path,
            form_definition_id=form_definition_id,
            form_definition_version_id=form_definition_version_id,
            title=title,
            description=description,
            attributes=attributes,
            price=price,
            location=location,
            lifecycle_state=LifecycleState.DRAFT,
            is_flagged=False,
            awaiting_payment=False,
            expires_at=None,
            published_at=None,
            promotion=None,
            slug=slug,
            images=(),
            transitions=(transition,),
            created_at=now,
            updated_at=now,
        )

    # --- visibility (I-06, the single authoritative rule) --------------------------------------

    def is_publicly_visible(self, *, now: datetime) -> bool:
        """I-06: "publicly visible only in Published/Edited states, unflagged, unexpired." The
        Physical DB's own partial index deliberately does *not* filter on `expires_at` (applied
        at query time instead) -- this method is that runtime predicate, the one place it is
        evaluated, so `interfaces/`/`infrastructure/` query code calls this rather than
        re-deriving the same three conditions."""
        if self.lifecycle_state not in _VISIBLE_STATES:
            return False
        if self.is_flagged:
            return False
        return self.expires_at is None or self.expires_at > now

    # --- internal transition-record helper ------------------------------------------------------

    def _record(
        self,
        *,
        to_state: LifecycleState,
        kind: TransitionKind,
        actor_user_id: UUID | None,
        reason: str | None,
        record_id: UUID,
        now: datetime,
    ) -> LifecycleTransitionRecord:
        return LifecycleTransitionRecord(
            id=record_id,
            from_state=self.lifecycle_state,
            to_state=to_state,
            transition_kind=kind,
            actor_user_id=actor_user_id,
            reason=reason,
            occurred_at=now,
        )

    # --- lifecycle transitions (I-05; FR-ADV-004/005/006/007) -----------------------------------

    def publish(
        self,
        *,
        record_id: UUID,
        actor_user_id: UUID,
        expires_at: datetime,
        now: datetime,
    ) -> Listing:
        """FR-ADV-004/BRULE-17: first-time publication only (`DRAFT -> PUBLISHED`); bringing back
        a shelved listing is `restore`, a distinct method/verb. `published_at` is set once and
        never overwritten (Physical DB `ck_published_has_ts` requires it non-null in
        PUBLISHED/EDITED, and "first publication" is its own documented meaning). `expires_at` is
        computed by the caller from the configured expiry period (FR-ADV-007, `application/`'s
        `PlatformSettingsReaderPort` -- DEC-21: never hardcode a configurable value) and starts
        the ExpiryTerm the sweep worker later acts on; `renew` is the only other method that ever
        moves it afterwards. Fires regardless of `is_flagged` -- I-06's visibility rule is
        evaluated by `is_publicly_visible`, not by withholding the state transition itself
        (BRULE-17: a flagged listing is `PUBLISHED` but not *visible*, exactly the "withheld,
        held for moderation" behaviour, realised as one predicate rather than a queued sub-state)."""
        if self.lifecycle_state is not LifecycleState.DRAFT:
            raise IllegalListingStateTransitionError("publish", self.lifecycle_state.value)
        record = self._record(
            to_state=LifecycleState.PUBLISHED,
            kind=TransitionKind.PUBLISH,
            actor_user_id=actor_user_id,
            reason=None,
            record_id=record_id,
            now=now,
        )
        return replace(
            self,
            lifecycle_state=LifecycleState.PUBLISHED,
            awaiting_payment=False,
            published_at=self.published_at or now,
            expires_at=self.expires_at or expires_at,
            transitions=(*self.transitions, record),
            updated_at=now,
        )

    def edit_content(
        self,
        *,
        record_id: UUID,
        actor_user_id: UUID,
        now: datetime,
        form_definition_id: UUID,
        form_definition_version_id: UUID,
        title: str | None = None,
        description: str | None = None,
        attributes: dict[str, Any] | None = None,
        price: Money | None = None,
        location: GeoLocation | None = None,
    ) -> Listing:
        """FR-ADV-005: "the system SHALL allow the owner to edit a listing, transitioning it to
        the Edited state." A `DRAFT` stays `DRAFT` (never published, nothing to mark "edited");
        `PUBLISHED`/`EDITED` both move to `EDITED`. Every call still appends an `EDIT` record
        regardless of whether the state value itself changes -- the append-only history is the
        `EditHistoryMarker` (FR-ADV-005's own acceptance criterion), distinct from whether
        `lifecycle_state` moved. `attributes` here is already validated by the caller
        (`policies.py::validate_attribute_set`, module docstring) against the *new*
        `form_definition_id`/`form_definition_version_id` `application/` resolved as current --
        this method just records the rebinding (I-07, see the field's own docstring); it trusts
        both its scalar input and the pre-validated attributes the same way
        `identity.application.account_use_cases` trusts its callers."""
        if self.lifecycle_state not in (
            LifecycleState.DRAFT,
            LifecycleState.PUBLISHED,
            LifecycleState.EDITED,
        ):
            raise IllegalListingStateTransitionError("edit", self.lifecycle_state.value)
        to_state = (
            LifecycleState.EDITED
            if self.lifecycle_state in (LifecycleState.PUBLISHED, LifecycleState.EDITED)
            else LifecycleState.DRAFT
        )
        record = self._record(
            to_state=to_state,
            kind=TransitionKind.EDIT,
            actor_user_id=actor_user_id,
            reason=None,
            record_id=record_id,
            now=now,
        )
        return replace(
            self,
            form_definition_id=form_definition_id,
            form_definition_version_id=form_definition_version_id,
            title=title if title is not None else self.title,
            description=description if description is not None else self.description,
            attributes=attributes if attributes is not None else self.attributes,
            price=price if price is not None else self.price,
            location=location if location is not None else self.location,
            lifecycle_state=to_state,
            transitions=(*self.transitions, record),
            updated_at=now,
        )

    def suspend(
        self,
        *,
        record_id: UUID,
        actor_user_id: UUID | None,
        reason: str | None,
        now: datetime,
    ) -> Listing:
        """`actor_user_id` may be `None` for a system-driven suspension with no acting user in
        scope (e.g. a lapsed business-profile subscription, `ListingUseCases.
        suspend_all_by_owner_profile`) -- the same "system-driven, no actor" case `record_expiry`
        already establishes for `EXPIRE`, just reachable from a second transition kind."""
        if self.lifecycle_state not in _VISIBLE_STATES:
            raise IllegalListingStateTransitionError("suspend", self.lifecycle_state.value)
        record = self._record(
            to_state=LifecycleState.SUSPENDED,
            kind=TransitionKind.SUSPEND,
            actor_user_id=actor_user_id,
            reason=reason,
            record_id=record_id,
            now=now,
        )
        return replace(
            self,
            lifecycle_state=LifecycleState.SUSPENDED,
            transitions=(*self.transitions, record),
            updated_at=now,
        )

    def archive(
        self, *, record_id: UUID, actor_user_id: UUID, reason: str | None, now: datetime
    ) -> Listing:
        if self.lifecycle_state not in (*_VISIBLE_STATES, LifecycleState.SUSPENDED):
            raise IllegalListingStateTransitionError("archive", self.lifecycle_state.value)
        record = self._record(
            to_state=LifecycleState.ARCHIVED,
            kind=TransitionKind.ARCHIVE,
            actor_user_id=actor_user_id,
            reason=reason,
            record_id=record_id,
            now=now,
        )
        return replace(
            self,
            lifecycle_state=LifecycleState.ARCHIVED,
            transitions=(*self.transitions, record),
            updated_at=now,
        )

    def restore(
        self,
        *,
        record_id: UUID,
        actor_user_id: UUID | None,
        reason: str | None,
        now: datetime,
    ) -> Listing:
        """Brings a shelved listing (`SUSPENDED`/`ARCHIVED`) back to `PUBLISHED` -- the
        `ListingStatusChangeRequest.action="RESTORE"` verb. No dedicated `ListingRestored` event
        exists in the frozen `contracts/events/catalog.py` catalogue (12 events, all present
        since Task P-01); `application/` republishes `ListingPublished` for this transition,
        the closest semantic fit ("the listing becomes publicly visible again", exactly what
        `ListingPublished`'s own consumers -- Search/Notifications/Analytics -- need to hear).
        `actor_user_id` may be `None` for the same system-driven reason `suspend`'s own docstring
        gives (a renewed business-profile subscription reactivating its listings in bulk)."""
        if self.lifecycle_state not in (
            LifecycleState.SUSPENDED,
            LifecycleState.ARCHIVED,
        ):
            raise IllegalListingStateTransitionError("restore", self.lifecycle_state.value)
        record = self._record(
            to_state=LifecycleState.PUBLISHED,
            kind=TransitionKind.RESTORE,
            actor_user_id=actor_user_id,
            reason=reason,
            record_id=record_id,
            now=now,
        )
        return replace(
            self,
            lifecycle_state=LifecycleState.PUBLISHED,
            transitions=(*self.transitions, record),
            updated_at=now,
        )

    def renew(
        self,
        *,
        record_id: UUID,
        actor_user_id: UUID,
        new_expires_at: datetime,
        now: datetime,
    ) -> Listing:
        """FR-ADV-007: renewal restores visibility by extending `expires_at`; `lifecycle_state`
        itself never changed on expiry (see `record_expiry`), so renewal never changes it either
        -- only the timestamp moves, recorded as a `RENEW` transition (`from_state == to_state`,
        matching "Renewed as a RECORDED transition", not a state)."""
        if self.lifecycle_state not in _VISIBLE_STATES:
            raise IllegalListingStateTransitionError("renew", self.lifecycle_state.value)
        record = self._record(
            to_state=self.lifecycle_state,
            kind=TransitionKind.RENEW,
            actor_user_id=actor_user_id,
            reason=None,
            record_id=record_id,
            now=now,
        )
        return replace(
            self,
            expires_at=new_expires_at,
            transitions=(*self.transitions, record),
            updated_at=now,
        )

    def delete(
        self,
        *,
        record_id: UUID,
        actor_user_id: UUID | None,
        reason: str | None,
        now: datetime,
    ) -> Listing:
        """ "Deleted" is a STATE, never a row removal (DM-06 -- a guard trigger blocks physical
        DELETE at the database level, same discipline `identity.domain.UserAccount.close` already
        uses for anonymise-not-erase)."""
        if self.lifecycle_state is LifecycleState.DELETED:
            raise IllegalListingStateTransitionError("delete", self.lifecycle_state.value)
        record = self._record(
            to_state=LifecycleState.DELETED,
            kind=TransitionKind.DELETE,
            actor_user_id=actor_user_id,
            reason=reason,
            record_id=record_id,
            now=now,
        )
        return replace(
            self,
            lifecycle_state=LifecycleState.DELETED,
            transitions=(*self.transitions, record),
            updated_at=now,
        )

    def record_expiry(self, *, record_id: UUID, now: datetime) -> Listing:
        """Worker-only (the expiry sweep, never an owner-invoked API action -- no `EXPIRE` value
        exists in `ListingStatusChangeRequest.action`'s enum). `lifecycle_state` never changes
        (see `renew`'s docstring); idempotent by construction: if the most recent transition is
        already `EXPIRE`, this is a no-op rather than appending a duplicate -- the sweep worker's
        query re-selecting the same still-expired-and-unrenewed listing on a later poll must not
        re-fire `ListingExpired` every cycle."""
        if self.lifecycle_state not in _VISIBLE_STATES:
            raise IllegalListingStateTransitionError("expire", self.lifecycle_state.value)
        if self.transitions and self.transitions[-1].transition_kind is TransitionKind.EXPIRE:
            return self
        record = self._record(
            to_state=self.lifecycle_state,
            kind=TransitionKind.EXPIRE,
            actor_user_id=None,
            reason=None,
            record_id=record_id,
            now=now,
        )
        return replace(self, transitions=(*self.transitions, record), updated_at=now)

    # --- flagging (I-06, BRULE-17; DuplicateDetectionService/moderation command port) -----------

    def flag(self, *, record_id: UUID, reason: str | None, now: datetime) -> Listing:
        """BRULE-17: an automated-validation or duplicate-detection hit withholds the listing
        from public visibility without changing `lifecycle_state` -- I-06 treats `is_flagged` as
        an independent dimension. Reachable from any non-`DELETED` state (a `DRAFT` can be
        pre-flagged by duplicate detection before its owner ever publishes it)."""
        if self.lifecycle_state is LifecycleState.DELETED:
            raise IllegalListingStateTransitionError("flag", self.lifecycle_state.value)
        if self.is_flagged:
            raise ListingAlreadyFlaggedError()
        record = self._record(
            to_state=self.lifecycle_state,
            kind=TransitionKind.FLAG,
            actor_user_id=None,
            reason=reason,
            record_id=record_id,
            now=now,
        )
        return replace(
            self,
            is_flagged=True,
            transitions=(*self.transitions, record),
            updated_at=now,
        )

    def unflag(self, *, record_id: UUID, reason: str | None, now: datetime) -> Listing:
        """No dedicated event exists for `UNFLAG` in the frozen catalogue (same governance
        boundary as `restore`'s docstring) -- `application/` records the transition only, no
        event publish. Not reachable via `changeListingStatus` (`UNFLAG` is absent from
        `ListingStatusChangeRequest.action`'s enum) -- this is the moderation command port's
        method, per this task's own Deliverables ("the listing state-transition command port
        that moderation will later invoke"), see `interfaces/moderation_port.py`."""
        if not self.is_flagged:
            raise ListingNotFlaggedError()
        record = self._record(
            to_state=self.lifecycle_state,
            kind=TransitionKind.UNFLAG,
            actor_user_id=None,
            reason=reason,
            record_id=record_id,
            now=now,
        )
        return replace(
            self,
            is_flagged=False,
            transitions=(*self.transitions, record),
            updated_at=now,
        )

    # --- images (I-04, BRULE-06/11; ordered, <=10) -----------------------------------------------

    def attach_image(
        self,
        *,
        image_id: UUID,
        media_asset_id: UUID,
        now: datetime,
        status: ImageStatus = ImageStatus.PENDING,
    ) -> Listing:
        """`status` defaults to PENDING -- scanning is asynchronous and attaching never blocks on
        media's pipeline (QR-05).

        The caller passes the asset's *already known* status when it has one. Scanning frequently
        finishes before the owner gets around to attaching the image, and media's
        `MediaAssetReady` is consumed once: the projection looks up the listing currently holding
        the asset, finds none (nothing has attached it yet), and correctly no-ops. Nothing
        re-examines that asset afterwards, so an attachment created as PENDING for an
        already-scanned asset stayed PENDING for the rest of its life -- and the interface shows
        only CLEAN images, so a perfectly good photo was invisible forever. Seeding from the
        status the attach path has already fetched closes that window; the event still covers the
        other order, where the scan lands after the attach.
        """
        if len(self.images) >= MAX_IMAGE_ATTACHMENTS:
            raise ImageLimitExceededError(MAX_IMAGE_ATTACHMENTS)
        attachment = ImageAttachment(
            id=image_id,
            media_asset_id=media_asset_id,
            position=len(self.images) + 1,
            status=status,
            created_at=now,
        )
        return replace(self, images=(*self.images, attachment), updated_at=now)

    def detach_image(self, image_id: UUID, *, now: datetime) -> Listing:
        if not any(image.id == image_id for image in self.images):
            raise ImageAttachmentNotFoundError(image_id)
        remaining = tuple(image for image in self.images if image.id != image_id)
        renumbered = tuple(
            replace(image, position=index + 1) for index, image in enumerate(remaining)
        )
        return replace(self, images=renumbered, updated_at=now)

    def reorder_images(self, ordered_image_ids: tuple[UUID, ...], *, now: datetime) -> Listing:
        """`order` (OpenAPI `ImageReorderRequest`) names attachment ids, not media asset ids --
        "position derives from array index; index 0 = primary" (position 1 in storage terms)."""
        current_ids = {image.id for image in self.images}
        if set(ordered_image_ids) != current_ids or len(ordered_image_ids) != len(self.images):
            raise DuplicateImagePositionError()
        by_id = {image.id: image for image in self.images}
        reordered = tuple(
            replace(by_id[image_id], position=index + 1)
            for index, image_id in enumerate(ordered_image_ids)
        )
        return replace(self, images=reordered, updated_at=now)

    def update_image_status(
        self, *, media_asset_id: UUID, status: ImageStatus, now: datetime
    ) -> Listing:
        """Applies media's projected scan status (X-06 `MediaAssetReady`/`MediaAssetRejected`).
        A no-op if this listing holds no attachment for `media_asset_id` (the event arrived for
        media not -- or no longer -- attached here; not an error, redelivery-safe). I-04: "every
        attachment references a Clean... MediaAsset" is realised as an eventual guarantee here --
        a `QUARANTINED` result auto-detaches the attachment rather than merely recording the
        status, since a quarantined asset must never remain listed (I-20's own delivery gate in
        `media.domain`, mirrored on this side of the reference)."""
        if not any(image.media_asset_id == media_asset_id for image in self.images):
            return self
        if status is ImageStatus.QUARANTINED:
            remaining = tuple(
                image for image in self.images if image.media_asset_id != media_asset_id
            )
            renumbered = tuple(
                replace(image, position=index + 1) for index, image in enumerate(remaining)
            )
            return replace(self, images=renumbered, updated_at=now)
        updated = tuple(
            replace(image, status=status) if image.media_asset_id == media_asset_id else image
            for image in self.images
        )
        return replace(self, images=updated, updated_at=now)

    # --- listing paywall (2026-08-23, orthogonal field, plain replace()) -------------------------

    def mark_awaiting_payment(self, *, now: datetime) -> Listing:
        """Same shape as `apply_promotion`/`clear_promotion` just below: a plain `replace()`, no
        guard clause, no `TransitionKind`/transition record -- `awaiting_payment` is orthogonal to
        `lifecycle_state`, not a transition of it. Called only by `ListingUseCases.create_listing`
        when `requires_payment=True`, on a listing that is always freshly `DRAFT` (never on an
        already-persisted one), so no state-guard is needed here the way `publish`/`suspend` need
        one."""
        return replace(self, awaiting_payment=True, updated_at=now)

    # --- promotion (DDD Sec 5.3 PromotionMarker; X-03, projected only) ---------------------------

    def apply_promotion(
        self,
        *,
        kind: PromotionKind,
        valid_until: datetime,
        entitlement_id: UUID,
        now: datetime,
    ) -> Listing:
        return replace(
            self,
            promotion=PromotionMarker(
                kind=kind, valid_until=valid_until, entitlement_id=entitlement_id
            ),
            updated_at=now,
        )

    def clear_promotion(self, *, now: datetime) -> Listing:
        return replace(self, promotion=None, updated_at=now)
