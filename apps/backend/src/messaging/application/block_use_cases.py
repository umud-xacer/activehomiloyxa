"""messaging/application -- `BlockUseCases`: `blockUser`, `unblockUser`, `listBlocks` (FR-MSG-004)."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from contracts.events.messaging import UserBlocked
from messaging.application.exceptions import BlockAlreadyExistsError
from messaging.application.ports import BlockRepository
from messaging.domain import Block
from shared_kernel import OutboxPort, UserId


class BlockUseCases:
    def __init__(self, *, blocks: BlockRepository, outbox: OutboxPort) -> None:
        self._blocks = blocks
        self._outbox = outbox

    async def block_user(
        self, *, blocker_user_id: UserId, blocked_user_id: UserId, now: datetime
    ) -> Block:
        if await self._blocks.exists(
            blocker_user_id=blocker_user_id.value, blocked_user_id=blocked_user_id.value
        ):
            raise BlockAlreadyExistsError(blocked_user_id.value)

        block = Block.create(
            block_id=uuid4(),
            blocker_user_id=blocker_user_id,
            blocked_user_id=blocked_user_id,
            now=now,
        )
        await self._blocks.add(block)
        await self._outbox.append(
            UserBlocked(
                event_id=uuid4(),
                occurred_at=now,
                actor=blocker_user_id.value,
                aggregate_type="Block",
                aggregate_id=block.id,
                payload={
                    "blockId": str(block.id),
                    "blockerUserId": str(blocker_user_id.value),
                    "blockedUserId": str(blocked_user_id.value),
                },
            )
        )
        return block

    async def unblock_user(self, *, blocker_user_id: UserId, blocked_user_id: UserId) -> None:
        """Idempotent: unblocking a pair that was never blocked is a no-op, matching `unblockUser`'s
        own 204-only documented response (no 404 case)."""
        await self._blocks.delete(
            blocker_user_id=blocker_user_id.value, blocked_user_id=blocked_user_id.value
        )

    async def list_my_blocks(self, *, blocker_user_id: UserId) -> tuple[Block, ...]:
        return await self._blocks.list_by_blocker(blocker_user_id.value)
