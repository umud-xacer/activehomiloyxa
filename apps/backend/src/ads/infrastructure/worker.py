"""The campaign schedule sweep worker (FR-BANNER-002; ADR-0004's own note that `pause`/`resume`
carry no event but `start`/`end` do). Mirrors `billing.infrastructure.worker.
EntitlementExpiryWorker`'s exact poll-loop shape: `run_once()`/`run_forever(stop_event)`, a fresh
`AsyncSession` per batch via `backbone.persistence.session_scope`. No inbound network surface.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from ads.application import CampaignUseCases
from ads.application.ports import SlotSnapshot
from ads.domain import CreativeStatus
from ads.infrastructure.persistence.repository import (
    SqlalchemyBannerCampaignRepository,
    SqlalchemyEntitlementProjectionRepository,
)
from backbone.outbox import OutboxWriter
from backbone.persistence import session_scope

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger(__name__)


class CampaignScheduleSweepWorker:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        outbox_model: type[DeclarativeBase],
        poll_interval_seconds: float = 15.0,
    ) -> None:
        self._session_factory = session_factory
        self._outbox_model = outbox_model
        self._poll_interval_seconds = poll_interval_seconds

    async def run_once(self) -> tuple[int, int]:
        """One sweep batch in a single fresh transaction. Returns `(started, ended)` -- each
        campaign's state transition and its outbox event append commit together (DEC-09)."""
        now = datetime.now(UTC)
        async with session_scope(self._session_factory) as session:
            use_cases = CampaignUseCases(
                campaigns=SqlalchemyBannerCampaignRepository(session),
                slots=_UnusedSlotReader(),
                creatives=_UnusedCreativeReader(),
                entitlements=SqlalchemyEntitlementProjectionRepository(session),
                outbox=OutboxWriter(session, self._outbox_model),
            )
            return await use_cases.sweep_schedule_transitions(now=now)

    async def run_forever(self, *, stop_event: asyncio.Event | None = None) -> None:
        stop_event = stop_event or asyncio.Event()
        while not stop_event.is_set():
            try:
                started, ended = await self.run_once()
            except Exception:
                logger.exception("campaign schedule sweep batch failed")
                started, ended = 0, 0
            if started == 0 and ended == 0:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop_event.wait(), timeout=self._poll_interval_seconds)


class _UnusedSlotReader:
    """`CampaignUseCases`'s constructor requires a `PlacementSlotReaderPort`/`CreativeReaderPort`
    collaborator, but `sweep_schedule_transitions` -- the only method this worker calls -- never
    touches either (it only transitions already-created campaigns by schedule time). Mirrors
    `catalog.infrastructure.event_projection.handle_media_event`'s own note about a narrow,
    worker-only path not needing every collaborator a full use-case constructor demands; a real
    call here would be a defect (nothing in this worker's own call path reaches these ports)."""

    async def get_slot_by_key(self, slot_key: str) -> SlotSnapshot | None:
        raise AssertionError("unreachable: the schedule sweep never resolves a slot")


class _UnusedCreativeReader:
    async def get_creative_status(self, media_asset_id: UUID) -> CreativeStatus:
        raise AssertionError("unreachable: the schedule sweep never reads creative status")
