"""`SqlalchemyBannerCampaignRepository`/`SqlalchemyEntitlementProjectionRepository` -- implement
`application.ports`' repositories against Postgres. Maps persistence-ignorant domain aggregates
to/from ORM rows (DB Architecture Sec 18 "mapping lives in infrastructure/"). Mirrors
`billing.infrastructure.persistence.repository`'s cursor-pagination/`save()` patterns exactly.
"""

from __future__ import annotations

import base64
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ads.application.ports import EntitlementSnapshot
from ads.domain import BannerCampaign, CampaignStatus, CreativeStatus, Schedule, Targeting
from ads.infrastructure.persistence.models import BannerCampaignRow, EntitlementProjectionRow

_SERVE_CANDIDATE_STATUSES = (CampaignStatus.SCHEDULED.value, CampaignStatus.RUNNING.value)


def _encode_cursor(created_at: datetime, row_id: UUID) -> str:
    raw = f"{created_at.isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    created_at_str, row_id = raw.split("|", 1)
    return datetime.fromisoformat(created_at_str), UUID(row_id)


def _campaign_to_domain(row: BannerCampaignRow) -> BannerCampaign:
    targeting_raw = row.targeting or {}
    return BannerCampaign(
        id=row.id,
        placement_slot_id=row.placement_slot_id,
        placement_slot_version_id=row.placement_slot_version_id,
        slot_key=row.slot_key,
        creative_media_asset_id=row.creative_media_asset_id,
        creative_status=CreativeStatus(row.creative_status),
        entitlement_id=row.entitlement_id,
        schedule=Schedule(start=row.schedule_start, end=row.schedule_end, priority=row.priority),
        targeting=Targeting(
            category_ids=tuple(UUID(c) for c in targeting_raw.get("categoryIds", [])),
            geo=targeting_raw.get("geo"),
            languages=tuple(targeting_raw.get("languages", [])),
        ),
        status=CampaignStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
        lock_version=row.lock_version,
    )


def _campaign_row_kwargs(campaign: BannerCampaign) -> dict[str, object]:
    return {
        "placement_slot_id": campaign.placement_slot_id,
        "placement_slot_version_id": campaign.placement_slot_version_id,
        "slot_key": campaign.slot_key,
        "creative_media_asset_id": campaign.creative_media_asset_id,
        "creative_status": campaign.creative_status.value,
        "entitlement_id": campaign.entitlement_id,
        "schedule_start": campaign.schedule.start,
        "schedule_end": campaign.schedule.end,
        "priority": campaign.schedule.priority,
        "targeting": {
            "categoryIds": [str(c) for c in campaign.targeting.category_ids],
            "geo": campaign.targeting.geo,
            "languages": list(campaign.targeting.languages),
        },
        "status": campaign.status.value,
    }


class SqlalchemyBannerCampaignRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, campaign_id: UUID) -> BannerCampaign | None:
        row = await self._session.get(BannerCampaignRow, campaign_id)
        return _campaign_to_domain(row) if row is not None else None

    async def add(self, campaign: BannerCampaign) -> None:
        kwargs = _campaign_row_kwargs(campaign)
        self._session.add(
            BannerCampaignRow(
                id=campaign.id,
                created_at=campaign.created_at,
                updated_at=campaign.updated_at,
                **kwargs,
            )
        )

    async def save(self, campaign: BannerCampaign) -> BannerCampaign:
        row = await self._session.get(BannerCampaignRow, campaign.id)
        if row is None:
            raise LookupError(f"BannerCampaignRow {campaign.id} not found for save()")
        for key, value in _campaign_row_kwargs(campaign).items():
            setattr(row, key, value)
        row.updated_at = campaign.updated_at
        await self._session.flush()
        return _campaign_to_domain(row)

    async def list_for_operator(
        self,
        *,
        status: CampaignStatus | None,
        slot_key: str | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[BannerCampaign], str | None]:
        stmt = (
            select(BannerCampaignRow)
            .order_by(BannerCampaignRow.created_at, BannerCampaignRow.id)
            .limit(limit + 1)
        )
        if status is not None:
            stmt = stmt.where(BannerCampaignRow.status == status.value)
        if slot_key is not None:
            stmt = stmt.where(BannerCampaignRow.slot_key == slot_key)
        if cursor is not None:
            created_at, row_id = _decode_cursor(cursor)
            stmt = stmt.where(
                (BannerCampaignRow.created_at > created_at)
                | ((BannerCampaignRow.created_at == created_at) & (BannerCampaignRow.id > row_id))
            )
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        next_cursor = None
        if len(rows) > limit:
            rows = rows[:limit]
            next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id)
        return [_campaign_to_domain(row) for row in rows], next_cursor

    async def list_candidates_for_serve(self, *, slot_key: str) -> tuple[BannerCampaign, ...]:
        stmt = (
            select(BannerCampaignRow)
            .where(
                BannerCampaignRow.slot_key == slot_key,
                BannerCampaignRow.status.in_(_SERVE_CANDIDATE_STATUSES),
            )
            .order_by(BannerCampaignRow.priority.desc(), BannerCampaignRow.created_at)
        )
        result = await self._session.execute(stmt)
        return tuple(_campaign_to_domain(row) for row in result.scalars().all())

    async def list_by_creative_media_asset_id(
        self, media_asset_id: UUID
    ) -> tuple[BannerCampaign, ...]:
        result = await self._session.execute(
            select(BannerCampaignRow).where(
                BannerCampaignRow.creative_media_asset_id == media_asset_id
            )
        )
        return tuple(_campaign_to_domain(row) for row in result.scalars().all())

    async def list_due_to_start(self, *, now: datetime) -> tuple[BannerCampaign, ...]:
        """`CampaignScheduleSweepWorker`'s own query: every `SCHEDULED` campaign whose
        `schedule.start` has arrived."""
        result = await self._session.execute(
            select(BannerCampaignRow).where(
                BannerCampaignRow.status == CampaignStatus.SCHEDULED.value,
                BannerCampaignRow.schedule_start <= now,
            )
        )
        return tuple(_campaign_to_domain(row) for row in result.scalars().all())

    async def list_due_to_end(self, *, now: datetime) -> tuple[BannerCampaign, ...]:
        """`CampaignScheduleSweepWorker`'s own query: every still-live campaign whose
        `schedule.end` has passed."""
        result = await self._session.execute(
            select(BannerCampaignRow).where(
                BannerCampaignRow.status.in_(
                    (*_SERVE_CANDIDATE_STATUSES, CampaignStatus.PAUSED.value)
                ),
                BannerCampaignRow.schedule_end <= now,
            )
        )
        return tuple(_campaign_to_domain(row) for row in result.scalars().all())


def _entitlement_projection_to_domain(row: EntitlementProjectionRow) -> EntitlementSnapshot:
    return EntitlementSnapshot(
        entitlement_id=row.entitlement_id,
        target_id=row.target_id,
        valid_from=row.valid_from,
        valid_until=row.valid_until,
        activation_state=row.activation_state,
    )


class SqlalchemyEntitlementProjectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, entitlement_id: UUID) -> EntitlementSnapshot | None:
        row = await self._session.get(EntitlementProjectionRow, entitlement_id)
        return _entitlement_projection_to_domain(row) if row is not None else None

    async def upsert(self, snapshot: EntitlementSnapshot) -> None:
        row = await self._session.get(EntitlementProjectionRow, snapshot.entitlement_id)
        if row is None:
            self._session.add(
                EntitlementProjectionRow(
                    entitlement_id=snapshot.entitlement_id,
                    target_id=snapshot.target_id,
                    valid_from=snapshot.valid_from,
                    valid_until=snapshot.valid_until,
                    activation_state=snapshot.activation_state,
                )
            )
        else:
            row.target_id = snapshot.target_id
            row.valid_from = snapshot.valid_from
            row.valid_until = snapshot.valid_until
            row.activation_state = snapshot.activation_state

    async def mark_state(self, entitlement_id: UUID, *, activation_state: str) -> None:
        row = await self._session.get(EntitlementProjectionRow, entitlement_id)
        if row is None:
            return
        row.activation_state = activation_state
