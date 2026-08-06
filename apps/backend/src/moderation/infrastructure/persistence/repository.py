"""`SqlalchemyModerationCaseRepository` -- implements `application.ports.ModerationCaseRepository`
against Postgres. Maps the persistence-ignorant `ModerationCase` aggregate to/from its ORM row
(DB Architecture Sec 18 "mapping lives in infrastructure/").
"""

from __future__ import annotations

import base64
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from moderation.domain import (
    CaseStatus,
    ModerationCase,
    Origin,
    OriginType,
    Resolution,
    ResolutionAction,
)
from moderation.domain.value_objects import Subject, SubjectType
from moderation.infrastructure.persistence.models import ModerationCaseRow


def _encode_cursor(created_at: datetime, row_id: UUID) -> str:
    raw = f"{created_at.isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    created_at_str, row_id = raw.split("|", 1)
    return datetime.fromisoformat(created_at_str), UUID(row_id)


def _case_to_domain(row: ModerationCaseRow) -> ModerationCase:
    origin = Origin(
        origin_type=OriginType(row.origin_type),
        report_reason=row.report_reason,
        rule_key=row.rule_key,
    )
    resolution = (
        Resolution(
            action=ResolutionAction(row.resolution_action),
            note=row.resolution_note,
            moderator_user_id=row.moderator_user_id,  # type: ignore[arg-type]
            resolved_at=row.resolved_at,  # type: ignore[arg-type]
        )
        if row.resolution_action is not None
        else None
    )
    return ModerationCase(
        id=row.id,
        subject=Subject(subject_type=SubjectType(row.subject_type), subject_id=row.subject_id),
        origin=origin,
        reporter_user_id=row.reporter_user_id,
        status=CaseStatus(row.status),
        resolution=resolution,
        created_at=row.created_at,
        updated_at=row.updated_at,
        lock_version=row.lock_version,
    )


def _apply_case_fields(row: ModerationCaseRow, case: ModerationCase) -> None:
    row.subject_type = case.subject.subject_type.value
    row.subject_id = case.subject.subject_id
    row.origin_type = case.origin.origin_type.value
    row.report_reason = case.origin.report_reason
    row.rule_key = case.origin.rule_key
    row.reporter_user_id = case.reporter_user_id
    row.status = case.status.value
    row.resolution_action = case.resolution.action.value if case.resolution else None
    row.resolution_note = case.resolution.note if case.resolution else None
    row.moderator_user_id = case.resolution.moderator_user_id if case.resolution else None
    row.resolved_at = case.resolution.resolved_at if case.resolution else None
    row.updated_at = case.updated_at


class SqlalchemyModerationCaseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, case_id: UUID) -> ModerationCase | None:
        row = await self._session.get(ModerationCaseRow, case_id)
        return _case_to_domain(row) if row is not None else None

    async def get_open_or_in_review_for_subject(
        self, subject_type: SubjectType, subject_id: UUID
    ) -> ModerationCase | None:
        result = await self._session.execute(
            select(ModerationCaseRow)
            .where(
                ModerationCaseRow.subject_type == subject_type.value,
                ModerationCaseRow.subject_id == subject_id,
                ModerationCaseRow.status.in_(("OPEN", "IN_REVIEW")),
            )
            .order_by(ModerationCaseRow.created_at.desc())
            .limit(1)
        )
        row = result.scalars().first()
        return _case_to_domain(row) if row is not None else None

    async def add(self, case: ModerationCase) -> None:
        row = ModerationCaseRow(id=case.id)
        _apply_case_fields(row, case)
        row.created_at = case.created_at
        self._session.add(row)
        await self._session.flush()

    async def save(self, case: ModerationCase) -> ModerationCase:
        row = await self._session.get(ModerationCaseRow, case.id)
        if row is None:
            raise LookupError(f"ModerationCaseRow {case.id} not found for save()")
        _apply_case_fields(row, case)
        await self._session.flush()
        # `lock_version` is a `version_id_col` (`backbone.persistence.AggregateMixin`) --
        # SQLAlchemy expires it after a versioned UPDATE; an explicit `refresh()` performs that
        # reload through the async session's own greenlet context (see `profiles.infrastructure.
        # persistence.repository.SqlalchemyBusinessProfileRepository.save`'s own comment for why
        # a bare attribute access afterward would otherwise raise `MissingGreenlet`).
        await self._session.refresh(row)
        return _case_to_domain(row)

    async def list_queue(
        self,
        *,
        status: CaseStatus | None,
        subject_type: SubjectType | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[ModerationCase], str | None]:
        stmt = (
            select(ModerationCaseRow)
            .order_by(ModerationCaseRow.created_at, ModerationCaseRow.id)
            .limit(limit + 1)
        )
        if status is not None:
            stmt = stmt.where(ModerationCaseRow.status == status.value)
        if subject_type is not None:
            stmt = stmt.where(ModerationCaseRow.subject_type == subject_type.value)
        if cursor is not None:
            created_at, row_id = _decode_cursor(cursor)
            stmt = stmt.where(
                (ModerationCaseRow.created_at > created_at)
                | ((ModerationCaseRow.created_at == created_at) & (ModerationCaseRow.id > row_id))
            )
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        next_cursor = None
        if len(rows) > limit:
            rows = rows[:limit]
            next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id)
        return [_case_to_domain(row) for row in rows], next_cursor
