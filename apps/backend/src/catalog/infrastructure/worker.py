"""The catalog expiry sweep worker (FR-ADV-006/007: scheduled expiry using "the P-03 worker
framework" -- the poll-loop shape `media.infrastructure.worker.MediaIntakeWorker` already
established: `run_once()`/`run_forever(stop_event)`, a fresh `AsyncSession` per batch via
`backbone.persistence.session_scope`). No inbound network surface -- a poll loop over
`ListingRepository.list_expiring`, not an HTTP server."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from backbone.outbox import OutboxWriter
from backbone.persistence import session_scope
from catalog.application import ListingUseCases
from catalog.application.duplicate_detection_service import DuplicateDetectionService
from catalog.application.ports import (
    CategoryFormPort,
    MediaAssetReaderPort,
    PlatformSettingsReaderPort,
)
from catalog.application.quota_service import QuotaEnforcementService
from catalog.infrastructure.persistence import SqlalchemyListingRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger(__name__)


class CatalogExpiryWorker:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        outbox_model: type[DeclarativeBase],
        categories: CategoryFormPort,
        settings: PlatformSettingsReaderPort,
        media: MediaAssetReaderPort,
        batch_size: int = 50,
        poll_interval_seconds: float = 30.0,
    ) -> None:
        self._session_factory = session_factory
        self._outbox_model = outbox_model
        self._categories = categories
        self._settings = settings
        self._media = media
        self._batch_size = batch_size
        self._poll_interval_seconds = poll_interval_seconds

    async def run_once(self) -> int:
        """One expiry sweep batch in a single fresh transaction. Returns the number of listings
        swept (state-transition + outbox event append committed together, DB Architecture Sec
        1.3's second sanctioned synchronous exception)."""
        now = datetime.now(UTC)
        async with session_scope(self._session_factory) as session:
            listings = SqlalchemyListingRepository(session)
            use_cases = ListingUseCases(
                listings=listings,
                categories=self._categories,
                settings=self._settings,
                media=self._media,
                outbox=OutboxWriter(session, self._outbox_model),
                quota=QuotaEnforcementService(subscriptions=_UnusedSubscriptions()),
                duplicates=DuplicateDetectionService(listings=listings),
                credit_balance=_UnusedCreditBalance(),
            )
            return await use_cases.sweep_expired(now=now, batch_size=self._batch_size)

    async def run_forever(self, *, stop_event: asyncio.Event | None = None) -> None:
        stop_event = stop_event or asyncio.Event()
        while not stop_event.is_set():
            try:
                swept = await self.run_once()
            except Exception:
                logger.exception("catalog expiry sweep batch failed")
                swept = 0
            if swept == 0:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop_event.wait(), timeout=self._poll_interval_seconds)


class _UnusedSubscriptions:
    """`sweep_expired` never reads quota -- `QuotaEnforcementService` is a required
    `ListingUseCases` collaborator only because `create_listing` needs it. Rather than making the
    use case class's constructor conditionally accept a narrower shape for this one worker-only
    method, this no-op stub satisfies `SubscriptionSnapshotRepository` structurally and is never
    actually called from this worker's code path."""

    async def get_for_profile(self, owner_profile_id: object) -> None:
        raise AssertionError("not reachable from CatalogExpiryWorker.run_once")

    async def upsert(self, snapshot: object) -> None:
        raise AssertionError("not reachable from CatalogExpiryWorker.run_once")


class _UnusedCreditBalance:
    """Listing paywall Phase 4 (2026-08-23): same reasoning as `_UnusedSubscriptions` above --
    `sweep_expired` never calls `create_listing`, so `CreditBalancePort` is only a required
    `ListingUseCases` collaborator on paper here."""

    async def consume_one_listing_credit(self, *, owner_profile_id: object) -> bool:
        raise AssertionError("not reachable from CatalogExpiryWorker.run_once")
