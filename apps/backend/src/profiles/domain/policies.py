"""profiles -- domain policies (DDD Sec 5.2 `Policies`). Pure functions/constants, no I/O."""

from __future__ import annotations

from datetime import datetime, timedelta

from profiles.domain.verification_case import VerificationCase

VERIFICATION_SLA_HOURS = 72
"""BRULE-05: "verification target SLA is defined and monitored (design phase sets the exact
value)" -- this task's own design-phase value (3 business days), a fixed platform [P] constant.
`profiles` cannot read a configured value here (SAD Sec 8.1: profiles may import `shared_kernel,
identity, media` only, not `configuration`), the same reasoning `catalog.domain.listing.
MAX_IMAGE_ATTACHMENTS` documents for its own fixed literal."""


def compute_sla_due_at(*, now: datetime) -> datetime:
    return now + timedelta(hours=VERIFICATION_SLA_HOURS)


def order_queue(cases: list[VerificationCase]) -> list[VerificationCase]:
    """`QueueOrderingPolicy` (DDD Sec 5.2, FR-MOD-005's own sibling policy for BC-11's queue) --
    earliest SLA deadline first, so a reviewer always sees the case most at risk of breaching its
    SLA at the top of the queue."""
    return sorted(cases, key=lambda case: case.sla_due_at)
