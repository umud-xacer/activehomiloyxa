"""Unit tests for `MediaCreativeStatusAdapter` against a fake `_MediaReader`."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from ads.domain import CreativeStatus
from ads.infrastructure.media_adapter import MediaCreativeStatusAdapter


class _FakeMediaReader:
    def __init__(self) -> None:
        self.assets: dict[UUID, object] = {}

    async def get_media(self, media_id: UUID) -> object:
        if media_id not in self.assets:
            raise LookupError(media_id)
        return self.assets[media_id]


@pytest.mark.asyncio
async def test_get_creative_status_translates_clean_scan_status() -> None:
    reader = _FakeMediaReader()
    media_id = uuid4()
    reader.assets[media_id] = SimpleNamespace(scan_status="CLEAN")
    adapter = MediaCreativeStatusAdapter(reader)
    assert await adapter.get_creative_status(media_id) is CreativeStatus.CLEAN


@pytest.mark.asyncio
async def test_get_creative_status_translates_quarantined_scan_status() -> None:
    reader = _FakeMediaReader()
    media_id = uuid4()
    reader.assets[media_id] = SimpleNamespace(scan_status="QUARANTINED")
    adapter = MediaCreativeStatusAdapter(reader)
    assert await adapter.get_creative_status(media_id) is CreativeStatus.QUARANTINED


@pytest.mark.asyncio
async def test_get_creative_status_fails_closed_to_pending_when_media_is_unreachable() -> None:
    """I-20: never delivered until proven clean -- an unreachable/unknown asset must never be
    treated as CLEAN by default."""
    reader = _FakeMediaReader()
    adapter = MediaCreativeStatusAdapter(reader)
    assert await adapter.get_creative_status(uuid4()) is CreativeStatus.PENDING
