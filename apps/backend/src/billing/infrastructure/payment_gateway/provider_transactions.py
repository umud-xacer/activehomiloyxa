"""ADR-0010. `ProviderTransaction` -- a plain infrastructure record, not a domain aggregate (no
repository-per-aggregate discipline applies: this is Payme/Click's own protocol bookkeeping, the
same "cache/ledger, not a business object" status `backbone.idempotency`'s `ProcessedEventRow` or
`backbone.outbox`'s `OutboxEventRow` already have in every other module). Lives in
`infrastructure/` only -- `payme.py`/`click.py` are the only callers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from billing.infrastructure.persistence.models import ProviderTransactionRow

Provider = Literal["PAYME", "CLICK", "MOCK"]
ProviderTransactionState = Literal["CREATED", "PERFORMED", "CANCELLED"]


@dataclass(frozen=True)
class ProviderTransaction:
    id: UUID
    invoice_id: UUID
    provider: Provider
    provider_transaction_id: str
    state: ProviderTransactionState
    amount: Decimal
    created_at: datetime
    performed_at: datetime | None
    cancelled_at: datetime | None
    cancel_reason: str | None


def _to_domain(row: ProviderTransactionRow) -> ProviderTransaction:
    return ProviderTransaction(
        id=row.id,
        invoice_id=row.invoice_id,
        provider=row.provider,  # type: ignore[arg-type]
        provider_transaction_id=row.provider_transaction_id,
        state=row.state,  # type: ignore[arg-type]
        amount=row.amount,
        created_at=row.created_at,
        performed_at=row.performed_at,
        cancelled_at=row.cancelled_at,
        cancel_reason=row.cancel_reason,
    )


class ProviderTransactionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, transaction_id: UUID) -> ProviderTransaction | None:
        row = await self._session.get(ProviderTransactionRow, transaction_id)
        return _to_domain(row) if row is not None else None

    async def get_by_invoice(
        self, invoice_id: UUID, *, provider: Provider
    ) -> ProviderTransaction | None:
        """At most one row per (invoice, provider) -- `ux_provider_transaction_invoice_provider`.
        Backs `CheckPerformTransaction`/`CreateTransaction`'s own idempotency (a retry with the
        SAME provider transaction id is a no-op; a DIFFERENT id for an invoice that already has
        one is Payme's own "order already has a transaction" error, -31050)."""
        result = await self._session.execute(
            select(ProviderTransactionRow).where(
                ProviderTransactionRow.invoice_id == invoice_id,
                ProviderTransactionRow.provider == provider,
            )
        )
        row = result.scalars().first()
        return _to_domain(row) if row is not None else None

    async def get_by_provider_transaction_id(
        self, *, provider: Provider, provider_transaction_id: str
    ) -> ProviderTransaction | None:
        """Backs `PerformTransaction`/`CancelTransaction`/`CheckTransaction` (Payme) and
        `Complete` (Click) -- both address the transaction by the PROVIDER's own id, not ours."""
        result = await self._session.execute(
            select(ProviderTransactionRow).where(
                ProviderTransactionRow.provider == provider,
                ProviderTransactionRow.provider_transaction_id
                == provider_transaction_id,
            )
        )
        row = result.scalars().first()
        return _to_domain(row) if row is not None else None

    async def create(
        self,
        *,
        transaction_id: UUID,
        invoice_id: UUID,
        provider: Provider,
        provider_transaction_id: str,
        amount: Decimal,
        now: datetime,
    ) -> ProviderTransaction:
        row = ProviderTransactionRow(
            id=transaction_id,
            invoice_id=invoice_id,
            provider=provider,
            provider_transaction_id=provider_transaction_id,
            state="CREATED",
            amount=amount,
            created_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return _to_domain(row)

    async def mark_performed(
        self, transaction_id: UUID, *, now: datetime
    ) -> ProviderTransaction:
        row = await self._session.get(ProviderTransactionRow, transaction_id)
        if row is None:
            raise LookupError(f"ProviderTransactionRow {transaction_id} not found")
        row.state = "PERFORMED"
        row.performed_at = now
        await self._session.flush()
        return _to_domain(row)

    async def list_between(
        self, *, provider: Provider, start: datetime, end: datetime
    ) -> list[ProviderTransaction]:
        """Backs Payme's `GetStatement` (reconciliation) -- every transaction of this provider
        created within `[start, end]`, oldest first."""
        result = await self._session.execute(
            select(ProviderTransactionRow)
            .where(
                ProviderTransactionRow.provider == provider,
                ProviderTransactionRow.created_at >= start,
                ProviderTransactionRow.created_at <= end,
            )
            .order_by(ProviderTransactionRow.created_at)
        )
        return [_to_domain(row) for row in result.scalars().all()]

    async def mark_cancelled(
        self, transaction_id: UUID, *, reason: str, now: datetime
    ) -> ProviderTransaction:
        row = await self._session.get(ProviderTransactionRow, transaction_id)
        if row is None:
            raise LookupError(f"ProviderTransactionRow {transaction_id} not found")
        row.state = "CANCELLED"
        row.cancelled_at = now
        row.cancel_reason = reason
        await self._session.flush()
        return _to_domain(row)
