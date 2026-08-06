"""`messaging.domain.block.Block` -- FR-MSG-004."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from messaging.domain import Block, SelfBlockError
from shared_kernel import UserId

_NOW = datetime(2026, 7, 12, tzinfo=UTC)


class TestBlockCreate:
    def test_create_builds_a_directed_pair(self) -> None:
        blocker = UserId(value=uuid4())
        blocked = UserId(value=uuid4())
        block = Block.create(
            block_id=uuid4(), blocker_user_id=blocker, blocked_user_id=blocked, now=_NOW
        )
        assert block.pair.blocker_user_id == blocker
        assert block.pair.blocked_user_id == blocked
        assert block.created_at == _NOW

    def test_self_block_raises(self) -> None:
        same = UserId(value=uuid4())
        with pytest.raises(SelfBlockError):
            Block.create(block_id=uuid4(), blocker_user_id=same, blocked_user_id=same, now=_NOW)
