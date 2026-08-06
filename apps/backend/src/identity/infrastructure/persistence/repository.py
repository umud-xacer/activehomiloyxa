"""`SqlalchemyUserAccountRepository` / `SqlalchemyOtpChallengeRepository` -- implement
`application.ports.UserAccountRepository`/`OtpChallengeRepository` against Postgres. Maps
persistence-ignorant domain aggregates to/from ORM rows (DB Architecture Sec 18 "mapping lives
in infrastructure/"). Child rows (`AuthenticationMethodRow`, `RoleAssignmentRow`) are replaced
wholesale on every `save()` -- simplest correct strategy for a small, rarely-changing child
collection, and keeps the whole aggregate's write inside the one `AsyncSession`/transaction the
composition root opened for this unit of work (never commits itself)."""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backbone.persistence import session_scope
from identity.domain import (
    AccountKind,
    AccountStatus,
    AuthenticationMethod,
    AuthMethodType,
    EmailAddress,
    NotificationPreferences,
    OtpChallenge,
    OtpPurpose,
    PhoneNumber,
    PhoneRevealMode,
    PrivacySettings,
    RegistrationDecision,
    RegistrationReviewStatus,
    RoleAssignment,
    UserAccount,
)
from identity.infrastructure.persistence.models import (
    AuthenticationMethodRow,
    OtpChallengeRow,
    RoleAssignmentRow,
    UserAccountRow,
)
from shared_kernel import BusinessProfileId, UserId


def _registration_decision_from_row(row: UserAccountRow) -> RegistrationDecision:
    """Only called once `row.review_decision_outcome is not None`; the write path (`save()` below)
    always sets `reviewer_id`/`decided_at` alongside `outcome` in the same assignment, so the two
    are non-null together in every row this repository itself ever wrote."""
    assert row.review_decision_outcome is not None
    assert row.review_decision_reviewer_id is not None
    assert row.review_decision_decided_at is not None
    return RegistrationDecision(
        outcome=RegistrationReviewStatus(row.review_decision_outcome),
        reason=row.review_decision_reason,
        reviewer_user_id=row.review_decision_reviewer_id,
        decided_at=row.review_decision_decided_at,
    )


def _account_to_domain(
    row: UserAccountRow,
    methods: list[AuthenticationMethodRow],
    roles: list[RoleAssignmentRow],
) -> UserAccount:
    return UserAccount(
        id=UserId(value=row.id),
        phone=PhoneNumber(row.phone) if row.phone else None,
        email=EmailAddress(row.email) if row.email else None,
        display_name=row.display_name,
        status=AccountStatus(row.status),
        privacy_settings=PrivacySettings(phone_reveal_mode=PhoneRevealMode(row.phone_reveal_mode)),
        notification_preferences=NotificationPreferences(
            email=row.notify_email, web_push=row.notify_web_push, sms=row.notify_sms
        ),
        owned_profile_ids=tuple(BusinessProfileId(value=UUID(v)) for v in row.owned_profile_ids),
        authentication_methods=tuple(
            AuthenticationMethod(
                method_type=AuthMethodType(m.method_type),
                identifier=m.identifier,
                verified_at=m.verified_at,
                added_at=m.added_at,
                password_hash=m.password_hash,
            )
            for m in methods
        ),
        role_assignments=tuple(
            RoleAssignment(
                role_definition_head_id=r.role_definition_head_id,
                role_definition_version_id=r.role_definition_version_id,
                role_code=r.role_code,
                acting_profile_id=(
                    BusinessProfileId(value=r.acting_profile_id) if r.acting_profile_id else None
                ),
                assigned_at=r.assigned_at,
                assigned_by=r.assigned_by,
            )
            for r in roles
        ),
        created_at=row.created_at,
        updated_at=row.updated_at,
        account_kind=AccountKind(row.account_kind),
        anketa=dict(row.anketa),
        review_status=RegistrationReviewStatus(row.review_status),
        review_decision=(
            _registration_decision_from_row(row)
            if row.review_decision_outcome is not None
            else None
        ),
        lock_version=row.lock_version,
    )


def _method_row(account_id: UUID, method: AuthenticationMethod) -> AuthenticationMethodRow:
    return AuthenticationMethodRow(
        account_id=account_id,
        method_type=method.method_type.value,
        identifier=method.identifier,
        verified_at=method.verified_at,
        added_at=method.added_at,
        password_hash=method.password_hash,
    )


def _role_row(account_id: UUID, role: RoleAssignment) -> RoleAssignmentRow:
    return RoleAssignmentRow(
        account_id=account_id,
        role_definition_head_id=role.role_definition_head_id,
        role_definition_version_id=role.role_definition_version_id,
        role_code=role.role_code,
        acting_profile_id=role.acting_profile_id.value if role.acting_profile_id else None,
        assigned_at=role.assigned_at,
        assigned_by=role.assigned_by,
    )


def _encode_cursor(created_at: datetime, row_id: UUID) -> str:
    raw = f"{created_at.isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    created_at_str, row_id = raw.split("|", 1)
    return datetime.fromisoformat(created_at_str), UUID(row_id)


class SqlalchemyUserAccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, account_id: UserId) -> UserAccount | None:
        row = await self._session.get(UserAccountRow, account_id.value)
        return await self._hydrate(row) if row is not None else None

    async def get_by_phone(self, phone: PhoneNumber) -> UserAccount | None:
        result = await self._session.execute(
            select(UserAccountRow).where(UserAccountRow.phone == phone.value)
        )
        row = result.scalar_one_or_none()
        return await self._hydrate(row) if row is not None else None

    async def get_by_email(self, email: EmailAddress) -> UserAccount | None:
        result = await self._session.execute(
            select(UserAccountRow).where(UserAccountRow.email == email.value)
        )
        row = result.scalar_one_or_none()
        return await self._hydrate(row) if row is not None else None

    async def add(self, account: UserAccount) -> None:
        """Flushes the parent row before adding children: without an ORM `relationship()`
        linking `UserAccountRow`/`AuthenticationMethodRow`/`RoleAssignmentRow` (deliberately
        plain FK columns only -- these child rows have no repository or identity of their own
        outside this aggregate), SQLAlchemy's unit-of-work does not reliably order INSERT
        statements across different mapped classes within one flush; an explicit flush here
        makes the parent-before-children order certain rather than incidental."""
        self._session.add(self._account_row(account))
        await self._session.flush()
        for method in account.authentication_methods:
            self._session.add(_method_row(account.id.value, method))
        for role in account.role_assignments:
            self._session.add(_role_row(account.id.value, role))

    async def save(self, account: UserAccount) -> None:
        row = await self._session.get(UserAccountRow, account.id.value)
        if row is None:
            raise LookupError(f"UserAccountRow {account.id.value} not found for save()")
        row.phone = account.phone.value if account.phone else None
        row.email = account.email.value if account.email else None
        row.display_name = account.display_name
        row.status = account.status.value
        row.phone_reveal_mode = account.privacy_settings.phone_reveal_mode.value
        row.notify_email = account.notification_preferences.email
        row.notify_web_push = account.notification_preferences.web_push
        row.notify_sms = account.notification_preferences.sms
        row.owned_profile_ids = [str(p.value) for p in account.owned_profile_ids]
        row.review_status = account.review_status.value
        if account.review_decision is not None:
            row.review_decision_outcome = account.review_decision.outcome.value
            row.review_decision_reason = account.review_decision.reason
            row.review_decision_reviewer_id = account.review_decision.reviewer_user_id
            row.review_decision_decided_at = account.review_decision.decided_at
        row.updated_at = account.updated_at

        await self._session.execute(
            delete(AuthenticationMethodRow).where(
                AuthenticationMethodRow.account_id == account.id.value
            )
        )
        await self._session.execute(
            delete(RoleAssignmentRow).where(RoleAssignmentRow.account_id == account.id.value)
        )
        await self._session.flush()
        for method in account.authentication_methods:
            self._session.add(_method_row(account.id.value, method))
        for role in account.role_assignments:
            self._session.add(_role_row(account.id.value, role))

    async def list_page(
        self, *, status: str | None, query: str | None, cursor: str | None, limit: int
    ) -> tuple[list[UserAccount], str | None]:
        stmt = (
            select(UserAccountRow)
            .order_by(UserAccountRow.created_at, UserAccountRow.id)
            .limit(limit + 1)
        )
        if status is not None:
            stmt = stmt.where(UserAccountRow.status == status)
        if query:
            like = f"%{query}%"
            stmt = stmt.where(
                or_(
                    UserAccountRow.email.ilike(like),
                    UserAccountRow.phone.ilike(like),
                    UserAccountRow.display_name.ilike(like),
                )
            )
        if cursor is not None:
            created_at, row_id = _decode_cursor(cursor)
            stmt = stmt.where(
                or_(
                    UserAccountRow.created_at > created_at,
                    (UserAccountRow.created_at == created_at) & (UserAccountRow.id > row_id),
                )
            )
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        next_cursor = None
        if len(rows) > limit:
            rows = rows[:limit]
            next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id)
        accounts = [await self._hydrate(row) for row in rows]
        return accounts, next_cursor

    async def list_pending_review(
        self, *, cursor: str | None, limit: int
    ) -> tuple[list[UserAccount], str | None]:
        """ADR-0007. Oldest-first (FIFO), mirrors `list_page`'s own cursor shape."""
        stmt = (
            select(UserAccountRow)
            .where(UserAccountRow.review_status == RegistrationReviewStatus.PENDING.value)
            .order_by(UserAccountRow.created_at, UserAccountRow.id)
            .limit(limit + 1)
        )
        if cursor is not None:
            created_at, row_id = _decode_cursor(cursor)
            stmt = stmt.where(
                or_(
                    UserAccountRow.created_at > created_at,
                    (UserAccountRow.created_at == created_at) & (UserAccountRow.id > row_id),
                )
            )
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        next_cursor = None
        if len(rows) > limit:
            rows = rows[:limit]
            next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id)
        accounts = [await self._hydrate(row) for row in rows]
        return accounts, next_cursor

    async def _hydrate(self, row: UserAccountRow) -> UserAccount:
        methods_result = await self._session.execute(
            select(AuthenticationMethodRow).where(AuthenticationMethodRow.account_id == row.id)
        )
        roles_result = await self._session.execute(
            select(RoleAssignmentRow).where(RoleAssignmentRow.account_id == row.id)
        )
        return _account_to_domain(
            row, list(methods_result.scalars().all()), list(roles_result.scalars().all())
        )

    @staticmethod
    def _account_row(account: UserAccount) -> UserAccountRow:
        return UserAccountRow(
            id=account.id.value,
            phone=account.phone.value if account.phone else None,
            email=account.email.value if account.email else None,
            display_name=account.display_name,
            status=account.status.value,
            phone_reveal_mode=account.privacy_settings.phone_reveal_mode.value,
            notify_email=account.notification_preferences.email,
            notify_web_push=account.notification_preferences.web_push,
            notify_sms=account.notification_preferences.sms,
            owned_profile_ids=[str(p.value) for p in account.owned_profile_ids],
            created_at=account.created_at,
            updated_at=account.updated_at,
            account_kind=account.account_kind.value,
            anketa=dict(account.anketa),
            review_status=account.review_status.value,
            review_decision_outcome=(
                account.review_decision.outcome.value if account.review_decision else None
            ),
            review_decision_reason=(
                account.review_decision.reason if account.review_decision else None
            ),
            review_decision_reviewer_id=(
                account.review_decision.reviewer_user_id if account.review_decision else None
            ),
            review_decision_decided_at=(
                account.review_decision.decided_at if account.review_decision else None
            ),
            lock_version=account.lock_version,
        )


def _challenge_to_domain(row: OtpChallengeRow) -> OtpChallenge:
    return OtpChallenge(
        id=row.id,
        phone=PhoneNumber(row.phone),
        purpose=OtpPurpose(row.purpose),
        code_hash=row.code_hash,
        attempts=row.attempts,
        max_attempts=row.max_attempts,
        created_at=row.created_at,
        expires_at=row.expires_at,
        consumed_at=row.consumed_at,
    )


class SqlalchemyOtpChallengeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active_for_phone(
        self, phone: PhoneNumber, purpose: OtpPurpose
    ) -> OtpChallenge | None:
        result = await self._session.execute(
            select(OtpChallengeRow)
            .where(
                OtpChallengeRow.phone == phone.value,
                OtpChallengeRow.purpose == purpose.value,
                OtpChallengeRow.consumed_at.is_(None),
            )
            .order_by(OtpChallengeRow.created_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return _challenge_to_domain(row) if row is not None else None

    async def add(self, challenge: OtpChallenge, *, ip_address: str) -> None:
        self._session.add(
            OtpChallengeRow(
                id=challenge.id,
                phone=challenge.phone.value,
                purpose=challenge.purpose.value,
                code_hash=challenge.code_hash,
                attempts=challenge.attempts,
                max_attempts=challenge.max_attempts,
                ip_address=ip_address,
                created_at=challenge.created_at,
                expires_at=challenge.expires_at,
                consumed_at=challenge.consumed_at,
            )
        )

    async def save(self, challenge: OtpChallenge) -> None:
        row = await self._session.get(OtpChallengeRow, challenge.id)
        if row is None:
            raise LookupError(f"OtpChallengeRow {challenge.id} not found for save()")
        row.attempts = challenge.attempts
        row.consumed_at = challenge.consumed_at

    async def count_recent_requests_by_phone(self, phone: PhoneNumber, *, since: datetime) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(OtpChallengeRow)
            .where(OtpChallengeRow.phone == phone.value, OtpChallengeRow.created_at >= since)
        )
        return int(result.scalar_one())

    async def count_recent_requests_by_ip(self, ip_address: str, *, since: datetime) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(OtpChallengeRow)
            .where(OtpChallengeRow.ip_address == ip_address, OtpChallengeRow.created_at >= since)
        )
        return int(result.scalar_one())


class SqlalchemyOtpChallengeUnitOfWork:
    """Implements `identity.application.ports.OtpChallengeUnitOfWork` (P-21 fix). Opens a BRAND
    NEW session per call via `session_scope` -- deliberately never the ambient session
    `AuthenticationUseCases`' other repositories share, so this transaction commits and its
    connection releases before `request_otp` goes on to call the SMS provider."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    @asynccontextmanager
    async def open(self) -> AsyncIterator[SqlalchemyOtpChallengeRepository]:
        async with session_scope(self._session_factory) as session:
            yield SqlalchemyOtpChallengeRepository(session)
