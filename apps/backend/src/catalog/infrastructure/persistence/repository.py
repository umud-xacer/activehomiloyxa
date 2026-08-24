"""`SqlalchemyListingRepository` / `SqlalchemyFavoriteRepository` /
`SqlalchemySubscriptionSnapshotRepository` -- implement `application.ports`' repositories against
Postgres. Maps persistence-ignorant domain aggregates to/from ORM rows (DB Architecture Sec 18
"mapping lives in infrastructure/"). Child rows (`ImageAttachmentRow`, `ListingTransitionRow`) are
replaced wholesale on every `save()` -- mirrors `identity.infrastructure.persistence.repository.
SqlalchemyUserAccountRepository`'s own documented strategy ("simplest correct strategy for a
small, rarely-changing child collection") and its parent-before-children flush ordering.
"""

from __future__ import annotations

import base64
from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.orm.exc import StaleDataError

from catalog.application.ports import SubscriptionSnapshot
from catalog.domain import (
    Favorite,
    ImageAttachment,
    LifecycleTransitionRecord,
    Listing,
)
from catalog.domain.value_objects import (
    ImageStatus,
    LifecycleState,
    ListingType,
    PromotionKind,
    PromotionMarker,
    TransitionKind,
)
from catalog.infrastructure.persistence.models import (
    FavoriteRow,
    ImageAttachmentRow,
    ListingRow,
    ListingTransitionRow,
    SubscriptionProjectionRow,
)
from shared_kernel import BusinessProfileId, GeoLocation, ListingId, Money, UserId


def _encode_cursor(created_at: datetime, row_id: UUID) -> str:
    raw = f"{created_at.isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    created_at_str, row_id = raw.split("|", 1)
    return datetime.fromisoformat(created_at_str), UUID(row_id)


def _image_to_domain(row: ImageAttachmentRow) -> ImageAttachment:
    return ImageAttachment(
        id=row.id,
        media_asset_id=row.media_asset_id,
        position=row.position,
        status=ImageStatus(row.asset_status_snapshot),
        created_at=row.created_at,
    )


def _image_row(listing_id: UUID, image: ImageAttachment) -> ImageAttachmentRow:
    return ImageAttachmentRow(
        id=image.id,
        listing_id=listing_id,
        media_asset_id=image.media_asset_id,
        position=image.position,
        asset_status_snapshot=image.status.value,
        created_at=image.created_at,
    )


def _transition_to_domain(row: ListingTransitionRow) -> LifecycleTransitionRecord:
    return LifecycleTransitionRecord(
        id=row.id,
        from_state=LifecycleState(row.from_state) if row.from_state else None,
        to_state=LifecycleState(row.to_state),
        transition_kind=TransitionKind(row.transition_kind),
        actor_user_id=row.actor_user_id,
        reason=row.reason,
        occurred_at=row.occurred_at,
    )


def _transition_row(listing_id: UUID, record: LifecycleTransitionRecord) -> ListingTransitionRow:
    return ListingTransitionRow(
        id=record.id,
        listing_id=listing_id,
        from_state=record.from_state.value if record.from_state else None,
        to_state=record.to_state.value,
        transition_kind=record.transition_kind.value,
        actor_user_id=record.actor_user_id,
        reason=record.reason,
        occurred_at=record.occurred_at,
    )


def _listing_to_domain(
    row: ListingRow,
    images: list[ImageAttachmentRow],
    transitions: list[ListingTransitionRow],
) -> Listing:
    price = (
        Money(amount=row.price_amount, currency=row.price_currency)
        if row.price_amount is not None and row.price_currency is not None
        else None
    )
    location = (
        GeoLocation(latitude=row.location_lat, longitude=row.location_long)
        if row.location_lat is not None and row.location_long is not None
        else None
    )
    promotion = (
        PromotionMarker(
            kind=PromotionKind(row.promotion_kind),
            valid_until=row.promotion_valid_until,  # type: ignore[arg-type]
            entitlement_id=row.promotion_entitlement_id,  # type: ignore[arg-type]
        )
        if row.promotion_kind is not None
        else None
    )
    return Listing(
        id=ListingId(value=row.id),
        listing_type=ListingType(row.listing_type),
        owner_user_id=UserId(value=row.owner_user_id),
        owner_profile_id=(
            BusinessProfileId(value=row.owner_profile_id) if row.owner_profile_id else None
        ),
        category_id=row.category_id,
        category_path=row.category_path,
        form_definition_id=row.form_definition_id,
        form_definition_version_id=row.form_definition_version_id,
        title=row.title,
        description=row.description,
        attributes=row.attribute_document,
        price=price,
        location=location,
        lifecycle_state=LifecycleState(row.lifecycle_state),
        is_flagged=row.is_flagged,
        awaiting_payment=row.awaiting_payment,
        expires_at=row.expires_at,
        published_at=row.published_at,
        promotion=promotion,
        slug=row.slug,
        images=tuple(_image_to_domain(i) for i in sorted(images, key=lambda i: i.position)),
        transitions=tuple(
            _transition_to_domain(t) for t in sorted(transitions, key=lambda t: t.occurred_at)
        ),
        created_at=row.created_at,
        updated_at=row.updated_at,
        lock_version=row.lock_version,
    )


def _listing_row(listing: Listing) -> ListingRow:
    return ListingRow(
        id=listing.id.value,
        listing_type=listing.listing_type.value,
        owner_user_id=listing.owner_user_id.value,
        owner_profile_id=listing.owner_profile_id.value if listing.owner_profile_id else None,
        category_id=listing.category_id,
        category_path=listing.category_path,
        form_definition_id=listing.form_definition_id,
        form_definition_version_id=listing.form_definition_version_id,
        title=listing.title,
        description=listing.description,
        attribute_document=listing.attributes,
        price_amount=listing.price.amount if listing.price else None,
        price_currency=listing.price.currency if listing.price else None,
        location_lat=listing.location.latitude if listing.location else None,
        location_long=listing.location.longitude if listing.location else None,
        lifecycle_state=listing.lifecycle_state.value,
        is_flagged=listing.is_flagged,
        awaiting_payment=listing.awaiting_payment,
        expires_at=listing.expires_at,
        published_at=listing.published_at,
        promotion_kind=listing.promotion.kind.value if listing.promotion else None,
        promotion_valid_until=listing.promotion.valid_until if listing.promotion else None,
        promotion_entitlement_id=listing.promotion.entitlement_id if listing.promotion else None,
        slug=listing.slug,
        created_at=listing.created_at,
        updated_at=listing.updated_at,
        lock_version=listing.lock_version,
    )


_VISIBLE_STATES = ("PUBLISHED", "EDITED")


class SqlalchemyListingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, listing_id: ListingId) -> Listing | None:
        row = await self._session.get(ListingRow, listing_id.value)
        return await self._hydrate(row) if row is not None else None

    async def add(self, listing: Listing) -> None:
        """Flushes the parent row before adding children -- see module docstring; no ORM
        `relationship()` links these classes, so the parent-before-children INSERT order is not
        otherwise guaranteed within one flush.

        The trailing flush matters just as much as the leading one (DEF-15). Sessions are created
        with `autoflush=False` (`backbone.persistence.engine.make_session_factory`), so leaving
        the child rows merely pending made this method's postcondition depend on whoever called it
        next. `save()` assumes the children it is about to `DELETE` are real rows: with them still
        pending, its `DELETE FROM listing_transition` matched nothing, its own `flush()` then
        inserted the pending CREATE row, and its re-add loop inserted a *second* row with the same
        primary key -- `IntegrityError` on `pk_listing_transition`. That made every
        `createListing` with `publish: true` fail with a 500, because `create_listing` calls
        `add()` and then `_do_publish()` -> `save()` with nothing flushing in between.

        Flushing here makes `add()` mean "persisted", which is what `save()` already relies on and
        what every test in `tests/catalog/integration/test_repository_live.py` was manually
        arranging with its own `flush()` call afterwards.
        """
        self._session.add(_listing_row(listing))
        await self._session.flush()
        for image in listing.images:
            self._session.add(_image_row(listing.id.value, image))
        for transition in listing.transitions:
            self._session.add(_transition_row(listing.id.value, transition))
        await self._session.flush()

    async def save(self, listing: Listing) -> Listing:
        row = await self._session.get(ListingRow, listing.id.value)
        if row is None:
            raise LookupError(f"ListingRow {listing.id.value} not found for save()")
        # `AsyncSession`'s identity map holds a *weak* reference to `row`: if nothing else keeps
        # it alive between an earlier `get_by_id()` and this call (the caller only holds the
        # detached `Listing` domain snapshot `_hydrate()` returned), the row can be garbage
        # collected and this `session.get()` silently re-fetches the *current* database state
        # instead of reusing the caller's original read. That refetch would carry today's
        # `lock_version`, not the version the caller's snapshot was taken at, which would make
        # `version_id_col`'s own UPDATE...WHERE check compare the fresh row against itself and
        # never detect a lost update. Comparing against the version on the `Listing` the caller
        # is actually trying to save closes that gap regardless of identity-map behaviour.
        if row.lock_version != listing.lock_version:
            raise StaleDataError(
                f"Listing {listing.id.value} has lock_version {row.lock_version} but save() was "
                f"called with a snapshot at lock_version {listing.lock_version}"
            )
        row.listing_type = listing.listing_type.value
        row.owner_profile_id = listing.owner_profile_id.value if listing.owner_profile_id else None
        row.category_id = listing.category_id
        row.category_path = listing.category_path
        row.form_definition_id = listing.form_definition_id
        row.form_definition_version_id = listing.form_definition_version_id
        row.title = listing.title
        row.description = listing.description
        row.attribute_document = listing.attributes
        row.price_amount = listing.price.amount if listing.price else None
        row.price_currency = listing.price.currency if listing.price else None
        row.location_lat = listing.location.latitude if listing.location else None
        row.location_long = listing.location.longitude if listing.location else None
        row.lifecycle_state = listing.lifecycle_state.value
        row.is_flagged = listing.is_flagged
        row.awaiting_payment = listing.awaiting_payment
        row.expires_at = listing.expires_at
        row.published_at = listing.published_at
        row.promotion_kind = listing.promotion.kind.value if listing.promotion else None
        row.promotion_valid_until = listing.promotion.valid_until if listing.promotion else None
        row.promotion_entitlement_id = (
            listing.promotion.entitlement_id if listing.promotion else None
        )
        row.slug = listing.slug
        row.updated_at = listing.updated_at
        # `save()` must enforce the optimistic-lock check on every call, not only when the
        # incoming values happen to differ from what's already loaded on `row` -- SQLAlchemy
        # elides the UPDATE (and therefore the `version_id_col` check) entirely when none of the
        # assigned column values actually changed, which would silently let a stale `listing`
        # "win" a lost-update race as long as its field values coincide with the current row.
        # `flag_modified` forces the UPDATE (and its version check) to run unconditionally.
        flag_modified(row, "updated_at")

        await self._session.execute(
            delete(ImageAttachmentRow).where(ImageAttachmentRow.listing_id == listing.id.value)
        )
        await self._session.execute(
            delete(ListingTransitionRow).where(ListingTransitionRow.listing_id == listing.id.value)
        )
        await self._session.flush()
        for image in listing.images:
            self._session.add(_image_row(listing.id.value, image))
        for transition in listing.transitions:
            self._session.add(_transition_row(listing.id.value, transition))
        await self._session.flush()
        # `lock_version` is a `version_id_col` (`backbone.persistence.AggregateMixin`) --
        # SQLAlchemy expires it after a versioned UPDATE so the next read reflects the
        # database's own post-increment value; an explicit `refresh()` performs that reload
        # through the async session's own greenlet context (a bare attribute access on `row`
        # afterward would try to lazy-load it outside that context and raise `MissingGreenlet`).
        # Pre-existing gap discovered and fixed via Task P-12's own account-suspension
        # compensation integration test (`apps/backend/tests/moderation/integration/
        # test_account_suspension_compensation_live.py`), the same bug class already fixed in
        # `profiles.infrastructure.persistence.repository`'s own `save()` methods during P-11.
        await self._session.refresh(row)
        return await self._hydrate(row)

    async def get_by_image_media_asset_id(self, media_asset_id: UUID) -> Listing | None:
        result = await self._session.execute(
            select(ImageAttachmentRow.listing_id).where(
                ImageAttachmentRow.media_asset_id == media_asset_id
            )
        )
        listing_row_id = result.scalars().first()
        if listing_row_id is None:
            return None
        row = await self._session.get(ListingRow, listing_row_id)
        return await self._hydrate(row) if row is not None else None

    async def list_by_owner(
        self,
        owner_user_id: UserId,
        *,
        state: str | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[Listing], str | None]:
        stmt = (
            select(ListingRow)
            .where(ListingRow.owner_user_id == owner_user_id.value)
            .order_by(ListingRow.created_at, ListingRow.id)
            .limit(limit + 1)
        )
        if state is not None:
            stmt = stmt.where(ListingRow.lifecycle_state == state)
        if cursor is not None:
            created_at, row_id = _decode_cursor(cursor)
            stmt = stmt.where(
                (ListingRow.created_at > created_at)
                | ((ListingRow.created_at == created_at) & (ListingRow.id > row_id))
            )
        return await self._execute_page(stmt, limit)

    async def list_by_owner_profile(
        self,
        owner_profile_id: BusinessProfileId,
        *,
        state: str | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[Listing], str | None]:
        stmt = (
            select(ListingRow)
            .where(ListingRow.owner_profile_id == owner_profile_id.value)
            .order_by(ListingRow.created_at, ListingRow.id)
            .limit(limit + 1)
        )
        if state is not None:
            stmt = stmt.where(ListingRow.lifecycle_state == state)
        if cursor is not None:
            created_at, row_id = _decode_cursor(cursor)
            stmt = stmt.where(
                (ListingRow.created_at > created_at)
                | ((ListingRow.created_at == created_at) & (ListingRow.id > row_id))
            )
        return await self._execute_page(stmt, limit)

    async def list_public(
        self,
        *,
        category_id: UUID | None,
        listing_type: str | None,
        cursor: str | None,
        limit: int,
        now: datetime,
    ) -> tuple[list[Listing], str | None]:
        stmt = (
            select(ListingRow)
            .where(
                ListingRow.lifecycle_state.in_(_VISIBLE_STATES),
                ListingRow.is_flagged.is_(False),
                (ListingRow.expires_at.is_(None)) | (ListingRow.expires_at > now),
            )
            .order_by(ListingRow.created_at, ListingRow.id)
            .limit(limit + 1)
        )
        if category_id is not None:
            stmt = stmt.where(ListingRow.category_id == category_id)
        if listing_type is not None:
            stmt = stmt.where(ListingRow.listing_type == listing_type)
        if cursor is not None:
            created_at, row_id = _decode_cursor(cursor)
            stmt = stmt.where(
                (ListingRow.created_at > created_at)
                | ((ListingRow.created_at == created_at) & (ListingRow.id > row_id))
            )
        return await self._execute_page(stmt, limit)

    async def list_expiring(self, *, now: datetime, limit: int) -> list[Listing]:
        stmt = (
            select(ListingRow)
            .where(
                ListingRow.lifecycle_state.in_(_VISIBLE_STATES),
                ListingRow.expires_at.is_not(None),
                ListingRow.expires_at <= now,
            )
            .order_by(ListingRow.expires_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        return [await self._hydrate(row) for row in rows]

    async def count_active_by_owner_profile(self, owner_profile_id: BusinessProfileId) -> int:
        """P-21 fix: was `select(ListingRow.id).where(...)` then `len(result.scalars().all())` --
        pulled every matching row's id across the wire just to count them, instead of letting
        Postgres compute the count directly. Called on every listing-creation quota check
        (I-08), so this ran once per create/publish attempt; at scale (a business profile with
        hundreds of active listings) that meant hundreds of UUIDs shipped over the wire for a
        number the database could return directly. Same result, same query predicate -- pure
        query-shape change, no behaviour change."""
        result = await self._session.execute(
            select(func.count())
            .select_from(ListingRow)
            .where(
                ListingRow.owner_profile_id == owner_profile_id.value,
                ListingRow.lifecycle_state != "DELETED",
            )
        )
        return int(result.scalar_one())

    async def find_recent_by_owner_category(
        self,
        *,
        owner_user_id: UserId,
        category_id: UUID,
        exclude_listing_id: ListingId | None,
        limit: int,
    ) -> list[Listing]:
        stmt = (
            select(ListingRow)
            .where(
                ListingRow.owner_user_id == owner_user_id.value,
                ListingRow.category_id == category_id,
            )
            .order_by(ListingRow.created_at.desc())
            .limit(limit)
        )
        if exclude_listing_id is not None:
            stmt = stmt.where(ListingRow.id != exclude_listing_id.value)
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        return [await self._hydrate(row) for row in rows]

    async def _execute_page(
        self, stmt: Select[tuple[ListingRow]], limit: int
    ) -> tuple[list[Listing], str | None]:
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        next_cursor = None
        if len(rows) > limit:
            rows = rows[:limit]
            next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id)
        listings = [await self._hydrate(row) for row in rows]
        return listings, next_cursor

    async def _hydrate(self, row: ListingRow) -> Listing:
        images_result = await self._session.execute(
            select(ImageAttachmentRow).where(ImageAttachmentRow.listing_id == row.id)
        )
        transitions_result = await self._session.execute(
            select(ListingTransitionRow).where(ListingTransitionRow.listing_id == row.id)
        )
        return _listing_to_domain(
            row,
            list(images_result.scalars().all()),
            list(transitions_result.scalars().all()),
        )


def _favorite_to_domain(row: FavoriteRow) -> Favorite:
    return Favorite(
        id=row.id,
        user_id=UserId(value=row.user_id),
        listing_id=ListingId(value=row.listing_id),
        created_at=row.created_at,
    )


class SqlalchemyFavoriteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, *, user_id: UserId, listing_id: ListingId) -> Favorite | None:
        result = await self._session.execute(
            select(FavoriteRow).where(
                FavoriteRow.user_id == user_id.value,
                FavoriteRow.listing_id == listing_id.value,
            )
        )
        row = result.scalar_one_or_none()
        return _favorite_to_domain(row) if row is not None else None

    async def add(self, favorite: Favorite) -> None:
        self._session.add(
            FavoriteRow(
                id=favorite.id,
                user_id=favorite.user_id.value,
                listing_id=favorite.listing_id.value,
                created_at=favorite.created_at,
            )
        )

    async def delete(self, *, user_id: UserId, listing_id: ListingId) -> None:
        await self._session.execute(
            delete(FavoriteRow).where(
                FavoriteRow.user_id == user_id.value,
                FavoriteRow.listing_id == listing_id.value,
            )
        )

    async def list_for_user(
        self, user_id: UserId, *, cursor: str | None, limit: int
    ) -> tuple[list[Favorite], str | None]:
        stmt = (
            select(FavoriteRow)
            .where(FavoriteRow.user_id == user_id.value)
            .order_by(FavoriteRow.created_at, FavoriteRow.id)
            .limit(limit + 1)
        )
        if cursor is not None:
            created_at, row_id = _decode_cursor(cursor)
            stmt = stmt.where(
                (FavoriteRow.created_at > created_at)
                | ((FavoriteRow.created_at == created_at) & (FavoriteRow.id > row_id))
            )
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        next_cursor = None
        if len(rows) > limit:
            rows = rows[:limit]
            next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id)
        return [_favorite_to_domain(row) for row in rows], next_cursor

    async def count_for_listing(self, listing_id: ListingId) -> int:
        result = await self._session.execute(
            select(FavoriteRow.id).where(FavoriteRow.listing_id == listing_id.value)
        )
        return len(result.scalars().all())


class SqlalchemySubscriptionSnapshotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_profile(
        self, owner_profile_id: BusinessProfileId
    ) -> SubscriptionSnapshot | None:
        row = await self._session.get(SubscriptionProjectionRow, owner_profile_id.value)
        if row is None:
            return None
        return SubscriptionSnapshot(
            owner_profile_id=BusinessProfileId(value=row.owner_profile_id),
            entitlement_id=row.entitlement_id,
            product_definition_id=row.product_definition_id,
            quota_document=row.quota_document,
            valid_until=row.valid_until,
            source_event_id=row.source_event_id,
        )

    async def upsert(self, snapshot: SubscriptionSnapshot) -> None:
        row = await self._session.get(SubscriptionProjectionRow, snapshot.owner_profile_id.value)
        if row is None:
            self._session.add(
                SubscriptionProjectionRow(
                    owner_profile_id=snapshot.owner_profile_id.value,
                    entitlement_id=snapshot.entitlement_id,
                    product_definition_id=snapshot.product_definition_id,
                    quota_document=snapshot.quota_document,
                    valid_until=snapshot.valid_until,
                    source_event_id=snapshot.source_event_id,
                )
            )
            return
        row.entitlement_id = snapshot.entitlement_id
        row.product_definition_id = snapshot.product_definition_id
        row.quota_document = snapshot.quota_document
        row.valid_until = snapshot.valid_until
        row.source_event_id = snapshot.source_event_id
