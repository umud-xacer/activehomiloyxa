"""messaging/application -- `ReportUseCases`: `createReport` (FR-MSG-005). Publishes
`ContentReported` for moderation (BC-11, later) to consume -- this task does NOT implement
moderation case handling (Excluded, P-10 prompt). No aggregate of messaging's own is persisted
here: a report is purely an outbox-published fact, routed by `subjectType` at the consuming end.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from contracts.events.messaging import ContentReported
from shared_kernel import OutboxPort, UserId


class ReportUseCases:
    def __init__(self, *, outbox: OutboxPort) -> None:
        self._outbox = outbox

    async def create_report(
        self,
        *,
        reporter_id: UserId,
        subject_type: Literal["LISTING", "CONVERSATION", "USER"],
        subject_id: UUID,
        reason: str,
        now: datetime,
    ) -> None:
        await self._outbox.append(
            ContentReported(
                event_id=uuid4(),
                occurred_at=now,
                actor=reporter_id.value,
                aggregate_type=subject_type.capitalize(),
                aggregate_id=subject_id,
                payload={
                    "subjectType": subject_type,
                    "subjectId": str(subject_id),
                    "reporterUserId": str(reporter_id.value),
                    "reason": reason,
                },
            )
        )
