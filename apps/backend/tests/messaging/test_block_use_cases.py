"""`messaging.application.block_use_cases.BlockUseCases` -- FR-MSG-004."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from messaging.application.block_use_cases import BlockUseCases
from messaging.application.exceptions import BlockAlreadyExistsError
from shared_kernel import UserId

from .conftest import FakeBlockRepository, FakeOutbox

_NOW = datetime(2026, 7, 12, tzinfo=UTC)


@pytest.fixture
def use_cases(fake_blocks: FakeBlockRepository, fake_outbox: FakeOutbox) -> BlockUseCases:
    return BlockUseCases(blocks=fake_blocks, outbox=fake_outbox)


class TestBlockUser:
    async def test_creates_a_block_and_emits_user_blocked(
        self, use_cases: BlockUseCases, fake_outbox: FakeOutbox
    ) -> None:
        blocker = UserId(value=uuid4())
        blocked = UserId(value=uuid4())
        block = await use_cases.block_user(
            blocker_user_id=blocker, blocked_user_id=blocked, now=_NOW
        )
        assert block.pair.blocker_user_id == blocker
        assert [e.event_type for e in fake_outbox.events] == ["UserBlocked"]

    async def test_duplicate_block_raises(self, use_cases: BlockUseCases) -> None:
        blocker = UserId(value=uuid4())
        blocked = UserId(value=uuid4())
        await use_cases.block_user(blocker_user_id=blocker, blocked_user_id=blocked, now=_NOW)
        with pytest.raises(BlockAlreadyExistsError):
            await use_cases.block_user(blocker_user_id=blocker, blocked_user_id=blocked, now=_NOW)


class TestUnblockUser:
    async def test_removes_an_existing_block(
        self, use_cases: BlockUseCases, fake_blocks: FakeBlockRepository
    ) -> None:
        blocker = UserId(value=uuid4())
        blocked = UserId(value=uuid4())
        await use_cases.block_user(blocker_user_id=blocker, blocked_user_id=blocked, now=_NOW)
        await use_cases.unblock_user(blocker_user_id=blocker, blocked_user_id=blocked)
        assert (
            await fake_blocks.exists(blocker_user_id=blocker.value, blocked_user_id=blocked.value)
            is False
        )

    async def test_unblocking_a_never_blocked_pair_is_a_no_op(
        self, use_cases: BlockUseCases
    ) -> None:
        await use_cases.unblock_user(
            blocker_user_id=UserId(value=uuid4()), blocked_user_id=UserId(value=uuid4())
        )


class TestListMyBlocks:
    async def test_returns_only_this_users_own_blocks(self, use_cases: BlockUseCases) -> None:
        blocker = UserId(value=uuid4())
        blocked_a = UserId(value=uuid4())
        blocked_b = UserId(value=uuid4())
        other_blocker = UserId(value=uuid4())
        await use_cases.block_user(blocker_user_id=blocker, blocked_user_id=blocked_a, now=_NOW)
        await use_cases.block_user(blocker_user_id=blocker, blocked_user_id=blocked_b, now=_NOW)
        await use_cases.block_user(
            blocker_user_id=other_blocker, blocked_user_id=UserId(value=uuid4()), now=_NOW
        )
        blocks = await use_cases.list_my_blocks(blocker_user_id=blocker)
        assert {b.pair.blocked_user_id for b in blocks} == {blocked_a, blocked_b}
