"""`SqlalchemyBusinessProfileRepository` / `SqlalchemyVerificationCaseRepository` /
`SqlalchemyVerificationEligibilityRepository` -- implement `application.ports`' repositories
against Postgres. Maps persistence-ignorant domain aggregates to/from ORM rows (DB Architecture
Sec 18 "mapping lives in infrastructure/"). Child rows (`PortfolioItemRow`/`SubmittedDocumentRow`)
are replaced wholesale on every `save()` -- mirrors `catalog.infrastructure.persistence.
repository.SqlalchemyListingRepository`'s own documented strategy.
"""

from __future__ import annotations

import base64
from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from profiles.application.ports import (
    SubscriptionEligibilitySnapshot,
    VerificationEligibilitySnapshot,
)
from profiles.domain import (
    BusinessProfile,
    CaseStatus,
    Decision,
    PortfolioItem,
    ProfileStatus,
    ProfileType,
    SubmittedDocument,
    VerificationCase,
    VerifiedBadge,
)
from profiles.domain.value_objects import BadgeStatus
from profiles.infrastructure.persistence.models import (
    BusinessProfileRow,
    PortfolioItemRow,
    SubmittedDocumentRow,
    SubscriptionEntitlementProjectionRow,
    VerificationCaseRow,
    VerificationEntitlementProjectionRow,
)
from shared_kernel import BusinessProfileId, LocalizedText, UserId


def _encode_cursor(created_at: datetime, row_id: UUID) -> str:
    raw = f"{created_at.isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    created_at_str, row_id = raw.split("|", 1)
    return datetime.fromisoformat(created_at_str), UUID(row_id)


def _localized_text(value: dict[str, object] | None) -> LocalizedText | None:
    return LocalizedText.model_validate(value) if value else None


def _portfolio_item_to_domain(row: PortfolioItemRow) -> PortfolioItem:
    return PortfolioItem(
        id=row.id,
        media_asset_id=row.media_asset_id,
        position=row.position,
        caption=_localized_text(row.caption_localized),
        created_at=row.created_at,
    )


def _portfolio_item_row(business_profile_id: UUID, item: PortfolioItem) -> PortfolioItemRow:
    return PortfolioItemRow(
        id=item.id,
        business_profile_id=business_profile_id,
        media_asset_id=item.media_asset_id,
        position=item.position,
        caption_localized=item.caption.model_dump(mode="json") if item.caption else None,
        created_at=item.created_at,
    )


def _profile_to_domain(
    row: BusinessProfileRow, portfolio: list[PortfolioItemRow]
) -> BusinessProfile:
    badge = (
        VerifiedBadge(
            status=BadgeStatus(row.badge_status),
            issued_at=row.badge_issued_at,  # type: ignore[arg-type]
            valid_until=row.badge_valid_until,  # type: ignore[arg-type]
        )
        if row.badge_status is not None
        else None
    )
    return BusinessProfile(
        id=BusinessProfileId(value=row.id),
        owner_user_id=UserId(value=row.owner_user_id),
        profile_type=ProfileType(row.profile_type),
        name=_localized_text(row.name_localized) or LocalizedText(),
        description=_localized_text(row.description_localized),
        contacts=dict(row.contacts),
        address=row.address,
        slug=row.slug,
        status=ProfileStatus(row.status),
        badge=badge,
        portfolio=tuple(
            _portfolio_item_to_domain(item) for item in sorted(portfolio, key=lambda i: i.position)
        ),
        logo_media_asset_id=row.logo_media_asset_id,
        banner_media_asset_id=row.banner_media_asset_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        lock_version=row.lock_version,
    )


def _apply_profile_fields(row: BusinessProfileRow, profile: BusinessProfile) -> None:
    row.owner_user_id = profile.owner_user_id.value
    row.profile_type = profile.profile_type.value
    row.name_localized = profile.name.model_dump(mode="json")
    row.description_localized = (
        profile.description.model_dump(mode="json") if profile.description else None
    )
    row.contacts = profile.contacts
    row.address = profile.address
    row.slug = profile.slug
    row.status = profile.status.value
    row.badge_status = profile.badge.status.value if profile.badge else None
    row.badge_issued_at = profile.badge.issued_at if profile.badge else None
    row.badge_valid_until = profile.badge.valid_until if profile.badge else None
    row.logo_media_asset_id = profile.logo_media_asset_id
    row.banner_media_asset_id = profile.banner_media_asset_id
    row.updated_at = profile.updated_at


class SqlalchemyBusinessProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, profile_id: BusinessProfileId) -> BusinessProfile | None:
        row = await self._session.get(BusinessProfileRow, profile_id.value)
        return await self._hydrate(row) if row is not None else None

    async def add(self, profile: BusinessProfile) -> None:
        row = BusinessProfileRow(id=profile.id.value)
        _apply_profile_fields(row, profile)
        row.created_at = profile.created_at
        self._session.add(row)
        await self._session.flush()
        for item in profile.portfolio:
            self._session.add(_portfolio_item_row(profile.id.value, item))
        await self._session.flush()

    async def save(self, profile: BusinessProfile) -> BusinessProfile:
        row = await self._session.get(BusinessProfileRow, profile.id.value)
        if row is None:
            raise LookupError(f"BusinessProfileRow {profile.id.value} not found for save()")
        _apply_profile_fields(row, profile)
        await self._session.execute(
            delete(PortfolioItemRow).where(PortfolioItemRow.business_profile_id == profile.id.value)
        )
        await self._session.flush()
        for item in profile.portfolio:
            self._session.add(_portfolio_item_row(profile.id.value, item))
        await self._session.flush()
        # `lock_version` is a `version_id_col` (`backbone.persistence.AggregateMixin`) --
        # SQLAlchemy expires it after a versioned UPDATE so the next read reflects the
        # database's own post-increment value; an explicit `refresh()` performs that reload
        # through the async session's own greenlet context (a bare attribute access on `row`
        # afterward would try to lazy-load it outside that context and raise `MissingGreenlet`).
        await self._session.refresh(row)
        return await self._hydrate(row)

    async def list_by_owner(
        self, owner_user_id: UserId, *, cursor: str | None, limit: int
    ) -> tuple[list[BusinessProfile], str | None]:
        stmt = (
            select(BusinessProfileRow)
            .where(BusinessProfileRow.owner_user_id == owner_user_id.value)
            .order_by(BusinessProfileRow.created_at, BusinessProfileRow.id)
            .limit(limit + 1)
        )
        if cursor is not None:
            created_at, row_id = _decode_cursor(cursor)
            stmt = stmt.where(
                (BusinessProfileRow.created_at > created_at)
                | ((BusinessProfileRow.created_at == created_at) & (BusinessProfileRow.id > row_id))
            )
        return await self._execute_page(stmt, limit)

    async def list_public(
        self,
        *,
        profile_type: ProfileType | None,
        verified_only: bool,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[BusinessProfile], str | None]:
        stmt = (
            select(BusinessProfileRow)
            .where(BusinessProfileRow.status != ProfileStatus.ARCHIVED.value)
            .order_by(BusinessProfileRow.created_at, BusinessProfileRow.id)
            .limit(limit + 1)
        )
        if profile_type is not None:
            stmt = stmt.where(BusinessProfileRow.profile_type == profile_type.value)
        if verified_only:
            stmt = stmt.where(BusinessProfileRow.badge_status == BadgeStatus.VALID.value)
        if cursor is not None:
            created_at, row_id = _decode_cursor(cursor)
            stmt = stmt.where(
                (BusinessProfileRow.created_at > created_at)
                | ((BusinessProfileRow.created_at == created_at) & (BusinessProfileRow.id > row_id))
            )
        return await self._execute_page(stmt, limit)

    async def list_admin(
        self, *, status: str | None, cursor: str | None, limit: int
    ) -> tuple[list[BusinessProfile], str | None]:
        stmt = (
            select(BusinessProfileRow)
            .order_by(BusinessProfileRow.created_at, BusinessProfileRow.id)
            .limit(limit + 1)
        )
        if status is not None:
            stmt = stmt.where(BusinessProfileRow.status == status)
        if cursor is not None:
            created_at, row_id = _decode_cursor(cursor)
            stmt = stmt.where(
                (BusinessProfileRow.created_at > created_at)
                | ((BusinessProfileRow.created_at == created_at) & (BusinessProfileRow.id > row_id))
            )
        return await self._execute_page(stmt, limit)

    async def count_all(self) -> int:
        result = await self._session.execute(select(func.count(BusinessProfileRow.id)))
        return int(result.scalar_one())

    async def get_by_portfolio_media_asset_id(self, media_asset_id: UUID) -> BusinessProfile | None:
        result = await self._session.execute(
            select(PortfolioItemRow.business_profile_id).where(
                PortfolioItemRow.media_asset_id == media_asset_id
            )
        )
        profile_row_id = result.scalars().first()
        if profile_row_id is None:
            return None
        row = await self._session.get(BusinessProfileRow, profile_row_id)
        return await self._hydrate(row) if row is not None else None

    async def list_badges_expiring(self, *, now: datetime, limit: int) -> list[BusinessProfile]:
        stmt = (
            select(BusinessProfileRow)
            .where(
                BusinessProfileRow.badge_status == BadgeStatus.VALID.value,
                BusinessProfileRow.badge_valid_until <= now,
            )
            .order_by(BusinessProfileRow.badge_valid_until)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        return [await self._hydrate(row) for row in rows]

    async def _execute_page(
        self, stmt: Select[tuple[BusinessProfileRow]], limit: int
    ) -> tuple[list[BusinessProfile], str | None]:
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        next_cursor = None
        if len(rows) > limit:
            rows = rows[:limit]
            next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id)
        profiles = [await self._hydrate(row) for row in rows]
        return profiles, next_cursor

    async def _hydrate(self, row: BusinessProfileRow) -> BusinessProfile:
        portfolio_result = await self._session.execute(
            select(PortfolioItemRow).where(PortfolioItemRow.business_profile_id == row.id)
        )
        return _profile_to_domain(row, list(portfolio_result.scalars().all()))


def _document_to_domain(row: SubmittedDocumentRow) -> SubmittedDocument:
    return SubmittedDocument(
        id=row.id,
        media_asset_id=row.media_asset_id,
        document_kind=row.document_kind,
        position=row.position,
        created_at=row.created_at,
    )


def _document_row(case_id: UUID, document: SubmittedDocument) -> SubmittedDocumentRow:
    return SubmittedDocumentRow(
        id=document.id,
        verification_case_id=case_id,
        media_asset_id=document.media_asset_id,
        document_kind=document.document_kind,
        position=document.position,
        created_at=document.created_at,
    )


def _case_to_domain(
    row: VerificationCaseRow, documents: list[SubmittedDocumentRow]
) -> VerificationCase:
    decision = (
        Decision(
            outcome=CaseStatus(row.decision_outcome),
            reason=row.decision_reason,
            reviewer_user_id=row.reviewer_user_id,  # type: ignore[arg-type]
            decided_at=row.decided_at,  # type: ignore[arg-type]
        )
        if row.decision_outcome is not None
        else None
    )
    return VerificationCase(
        id=row.id,
        business_profile_id=BusinessProfileId(value=row.business_profile_id),
        entitlement_id=row.entitlement_id,
        status=CaseStatus(row.status),
        sla_due_at=row.sla_due_at,
        documents=tuple(
            _document_to_domain(document)
            for document in sorted(documents, key=lambda d: d.position)
        ),
        decision=decision,
        created_at=row.created_at,
        updated_at=row.updated_at,
        lock_version=row.lock_version,
    )


def _apply_case_fields(row: VerificationCaseRow, case: VerificationCase) -> None:
    row.business_profile_id = case.business_profile_id.value
    row.entitlement_id = case.entitlement_id
    row.status = case.status.value
    row.sla_due_at = case.sla_due_at
    row.decision_outcome = case.decision.outcome.value if case.decision else None
    row.decision_reason = case.decision.reason if case.decision else None
    row.reviewer_user_id = case.decision.reviewer_user_id if case.decision else None
    row.decided_at = case.decision.decided_at if case.decision else None
    row.updated_at = case.updated_at


class SqlalchemyVerificationCaseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, case_id: UUID) -> VerificationCase | None:
        row = await self._session.get(VerificationCaseRow, case_id)
        return await self._hydrate(row) if row is not None else None

    async def get_current_for_profile(
        self, profile_id: BusinessProfileId
    ) -> VerificationCase | None:
        result = await self._session.execute(
            select(VerificationCaseRow)
            .where(VerificationCaseRow.business_profile_id == profile_id.value)
            .order_by(VerificationCaseRow.created_at.desc())
            .limit(1)
        )
        row = result.scalars().first()
        return await self._hydrate(row) if row is not None else None

    async def add(self, case: VerificationCase) -> None:
        row = VerificationCaseRow(id=case.id)
        _apply_case_fields(row, case)
        row.created_at = case.created_at
        self._session.add(row)
        await self._session.flush()
        for document in case.documents:
            self._session.add(_document_row(case.id, document))
        await self._session.flush()

    async def save(self, case: VerificationCase) -> VerificationCase:
        row = await self._session.get(VerificationCaseRow, case.id)
        if row is None:
            raise LookupError(f"VerificationCaseRow {case.id} not found for save()")
        _apply_case_fields(row, case)
        await self._session.execute(
            delete(SubmittedDocumentRow).where(SubmittedDocumentRow.verification_case_id == case.id)
        )
        await self._session.flush()
        for document in case.documents:
            self._session.add(_document_row(case.id, document))
        await self._session.flush()
        # See `SqlalchemyBusinessProfileRepository.save`'s own comment on why this is needed.
        await self._session.refresh(row)
        return await self._hydrate(row)

    async def list_queue(
        self, *, status: CaseStatus | None, cursor: str | None, limit: int
    ) -> tuple[list[VerificationCase], str | None]:
        stmt = (
            select(VerificationCaseRow)
            .order_by(VerificationCaseRow.sla_due_at, VerificationCaseRow.id)
            .limit(limit + 1)
        )
        if status is not None:
            stmt = stmt.where(VerificationCaseRow.status == status.value)
        if cursor is not None:
            sla_due_at, row_id = _decode_cursor(cursor)
            stmt = stmt.where(
                (VerificationCaseRow.sla_due_at > sla_due_at)
                | (
                    (VerificationCaseRow.sla_due_at == sla_due_at)
                    & (VerificationCaseRow.id > row_id)
                )
            )
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        next_cursor = None
        if len(rows) > limit:
            rows = rows[:limit]
            next_cursor = _encode_cursor(rows[-1].sla_due_at, rows[-1].id)
        cases = [await self._hydrate(row) for row in rows]
        return cases, next_cursor

    async def get_by_document_media_asset_id(self, media_asset_id: UUID) -> VerificationCase | None:
        result = await self._session.execute(
            select(SubmittedDocumentRow.verification_case_id).where(
                SubmittedDocumentRow.media_asset_id == media_asset_id
            )
        )
        case_row_id = result.scalars().first()
        if case_row_id is None:
            return None
        row = await self._session.get(VerificationCaseRow, case_row_id)
        return await self._hydrate(row) if row is not None else None

    async def _hydrate(self, row: VerificationCaseRow) -> VerificationCase:
        documents_result = await self._session.execute(
            select(SubmittedDocumentRow).where(SubmittedDocumentRow.verification_case_id == row.id)
        )
        return _case_to_domain(row, list(documents_result.scalars().all()))


class SqlalchemyVerificationEligibilityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active_for_profile(
        self, profile_id: BusinessProfileId, *, now: datetime
    ) -> VerificationEligibilitySnapshot | None:
        result = await self._session.execute(
            select(VerificationEntitlementProjectionRow)
            .where(
                VerificationEntitlementProjectionRow.business_profile_id == profile_id.value,
                VerificationEntitlementProjectionRow.activation_state == "ACTIVE",
                VerificationEntitlementProjectionRow.valid_until > now,
            )
            .order_by(VerificationEntitlementProjectionRow.valid_until.desc())
            .limit(1)
        )
        row = result.scalars().first()
        return _eligibility_to_domain(row) if row is not None else None

    async def get_by_entitlement_id(
        self, entitlement_id: UUID
    ) -> VerificationEligibilitySnapshot | None:
        row = await self._session.get(VerificationEntitlementProjectionRow, entitlement_id)
        return _eligibility_to_domain(row) if row is not None else None

    async def upsert(self, snapshot: VerificationEligibilitySnapshot) -> None:
        row = await self._session.get(VerificationEntitlementProjectionRow, snapshot.entitlement_id)
        if row is None:
            self._session.add(
                VerificationEntitlementProjectionRow(
                    entitlement_id=snapshot.entitlement_id,
                    business_profile_id=snapshot.business_profile_id.value,
                    valid_from=snapshot.valid_from,
                    valid_until=snapshot.valid_until,
                    activation_state=snapshot.activation_state,
                    source_event_id=snapshot.source_event_id,
                )
            )
            return
        row.business_profile_id = snapshot.business_profile_id.value
        row.valid_from = snapshot.valid_from
        row.valid_until = snapshot.valid_until
        row.activation_state = snapshot.activation_state
        row.source_event_id = snapshot.source_event_id


def _eligibility_to_domain(
    row: VerificationEntitlementProjectionRow,
) -> VerificationEligibilitySnapshot:
    return VerificationEligibilitySnapshot(
        entitlement_id=row.entitlement_id,
        business_profile_id=BusinessProfileId(value=row.business_profile_id),
        valid_from=row.valid_from,
        valid_until=row.valid_until,
        activation_state=row.activation_state,  # type: ignore[arg-type]
        source_event_id=row.source_event_id,
    )


class SqlalchemySubscriptionEligibilityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_profile(
        self, profile_id: BusinessProfileId
    ) -> SubscriptionEligibilitySnapshot | None:
        row = await self._session.get(SubscriptionEntitlementProjectionRow, profile_id.value)
        return _subscription_to_domain(row) if row is not None else None

    async def upsert(self, snapshot: SubscriptionEligibilitySnapshot) -> None:
        row = await self._session.get(
            SubscriptionEntitlementProjectionRow, snapshot.business_profile_id.value
        )
        if row is None:
            self._session.add(
                SubscriptionEntitlementProjectionRow(
                    business_profile_id=snapshot.business_profile_id.value,
                    entitlement_id=snapshot.entitlement_id,
                    valid_from=snapshot.valid_from,
                    valid_until=snapshot.valid_until,
                    activation_state=snapshot.activation_state,
                    source_event_id=snapshot.source_event_id,
                )
            )
            return
        row.entitlement_id = snapshot.entitlement_id
        row.valid_from = snapshot.valid_from
        row.valid_until = snapshot.valid_until
        row.activation_state = snapshot.activation_state
        row.source_event_id = snapshot.source_event_id


def _subscription_to_domain(
    row: SubscriptionEntitlementProjectionRow,
) -> SubscriptionEligibilitySnapshot:
    return SubscriptionEligibilitySnapshot(
        business_profile_id=BusinessProfileId(value=row.business_profile_id),
        entitlement_id=row.entitlement_id,
        valid_from=row.valid_from,
        valid_until=row.valid_until,
        activation_state=row.activation_state,  # type: ignore[arg-type]
        source_event_id=row.source_event_id,
    )
