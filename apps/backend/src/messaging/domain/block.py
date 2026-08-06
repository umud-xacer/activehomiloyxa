"""messaging/domain -- the `Block` aggregate (DDD Sec 5.7 `AR: Block [P]`): "a separate root --
consulted on every send/initiate, independent lifecycle." No state-transition methods beyond
creation: "unblock" is a physical `DELETE` (Physical DB Design: "physical DELETE on unblock
permitted -- facts persist as events"), not a guarded domain transition, so there is nothing for
a `Block.unblock()` method to guard.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from messaging.domain.value_objects import BlockPair
from shared_kernel import UserId


@dataclass(frozen=True)
class Block:
    id: UUID
    pair: BlockPair
    created_at: datetime

    @staticmethod
    def create(
        *, block_id: UUID, blocker_user_id: UserId, blocked_user_id: UserId, now: datetime
    ) -> Block:
        return Block(
            id=block_id,
            pair=BlockPair(blocker_user_id=blocker_user_id, blocked_user_id=blocked_user_id),
            created_at=now,
        )
