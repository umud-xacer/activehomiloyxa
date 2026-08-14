"""The profiles badge-expiry sweep worker (FR-PROF-006/007: "the system SHALL require
re-verification when a badge's validity period ends" -- "the P-03 worker framework" poll-loop
shape `catalog.infrastructure.worker.CatalogExpiryWorker` already established: `run_once()`/
`run_forever(stop_event)`, a fresh `AsyncSession` per batch via `backbone.persistence.
session_scope`). No inbound network surface -- a poll loop over
`BusinessProfileRepository.list_badges_expiring`, not an HTTP server.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from backbone.outbox import OutboxWriter
from backbone.persistence import session_scope
from profiles.application import ProfileUseCases
from profiles.infrastructure.persistence import (
    SqlalchemyBusinessProfileRepository,
    SqlalchemySubscriptionEligibilityRepository,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from sqlalchemy.orm import DeclarativeBase

    from profiles.application.ports import MediaAssetReaderPort

logger = logging.getLogger(__name__)


class BadgeExpiryWorker:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        outbox_model: type[DeclarativeBase],
        media: MediaAssetReaderPort,
        batch_size: int = 50,
        poll_interval_seconds: float = 60.0,
    ) -> None:
        self._session_factory = session_factory
        self._outbox_model = outbox_model
        self._media = media
        self._batch_size = batch_size
        self._poll_interval_seconds = poll_interval_seconds

    async def run_once(self) -> int:
        """One expiry sweep batch in a single fresh transaction. Returns the number of badges
        swept."""
        now = datetime.now(UTC)
        async with session_scope(self._session_factory) as session:
            profiles = SqlalchemyBusinessProfileRepository(session)
            use_cases = ProfileUseCases(
                profiles=profiles,
                media=self._media,
                outbox=OutboxWriter(session, self._outbox_model),
            )
            return await use_cases.sweep_expired_badges(now=now, batch_size=self._batch_size)

    async def run_forever(self, *, stop_event: asyncio.Event | None = None) -> None:
        stop_event = stop_event or asyncio.Event()
        while not stop_event.is_set():
            try:
                swept = await self.run_once()
            except Exception:
                logger.exception("profiles badge expiry sweep batch failed")
                swept = 0
            if swept == 0:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop_event.wait(), timeout=self._poll_interval_seconds)


class TrialExpiryWorker:
    """ADR-0010. Sweeps `BusinessProfile`s whose 5-day free trial (`trial_ends_at`) has passed
    with no paid subscription having superseded it -- same poll-loop shape as
    `BadgeExpiryWorker` above, run as a second, independent loop from `profiles_worker.py` (not
    merged into one worker class: the two sweeps have unrelated batch sizes/poll intervals and
    no shared state, mirroring how `catalog_worker.py` runs several independent dispatcher loops
    rather than one combined one)."""

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        outbox_model: type[DeclarativeBase],
        media: MediaAssetReaderPort,
        batch_size: int = 50,
        poll_interval_seconds: float = 60.0,
    ) -> None:
        self._session_factory = session_factory
        self._outbox_model = outbox_model
        self._media = media
        self._batch_size = batch_size
        self._poll_interval_seconds = poll_interval_seconds

    async def run_once(self) -> int:
        """One trial-expiry sweep batch in a single fresh transaction. Returns the number of
        trials swept."""
        now = datetime.now(UTC)
        async with session_scope(self._session_factory) as session:
            profiles = SqlalchemyBusinessProfileRepository(session)
            use_cases = ProfileUseCases(
                profiles=profiles,
                media=self._media,
                outbox=OutboxWriter(session, self._outbox_model),
                subscriptions=SqlalchemySubscriptionEligibilityRepository(session),
            )
            return await use_cases.sweep_expired_trials(now=now, batch_size=self._batch_size)

    async def run_forever(self, *, stop_event: asyncio.Event | None = None) -> None:
        stop_event = stop_event or asyncio.Event()
        while not stop_event.is_set():
            try:
                swept = await self.run_once()
            except Exception:
                logger.exception("profiles trial expiry sweep batch failed")
                swept = 0
            if swept == 0:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop_event.wait(), timeout=self._poll_interval_seconds)
