"""catalog -- the `LifecycleTransitionRecord` child entity (DDD Sec 5.3/DB Architecture Sec 1.3;
Physical DB `catalog.listing_transition`, append-only). I-05: "every transition is recorded" --
these rows are produced BY THE AGGREGATE (`Listing`'s own transition methods append one per
call), never assembled by the persistence layer after the fact. Also the physical realisation of
`EditHistoryMarker` (FR-ADV-005) and of "Expired/Renewed as recorded transitions" (FR-ADV-006/007)
-- `EXPIRE`/`RENEW` never change `lifecycle_state` but still append a record here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from catalog.domain.value_objects import LifecycleState, TransitionKind


@dataclass(frozen=True)
class LifecycleTransitionRecord:
    id: UUID
    from_state: LifecycleState | None
    """`None` only for the `CREATE` record (Physical DB: "states or NULL->DRAFT at creation")."""
    to_state: LifecycleState
    transition_kind: TransitionKind
    actor_user_id: UUID | None
    """`None` for system-driven transitions (the expiry sweep worker's `EXPIRE` records)."""
    reason: str | None
    occurred_at: datetime
