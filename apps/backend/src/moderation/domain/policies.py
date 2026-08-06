"""moderation -- domain policies (DDD Sec 5.11 `Policies`). Pure functions/constants, no I/O."""

from __future__ import annotations

from moderation.domain.moderation_case import ModerationCase


def order_queue(cases: list[ModerationCase]) -> list[ModerationCase]:
    """`QueueOrderingPolicy` (FR-MOD-005: "a moderation queue of reports and flagged content...
    queued items are listed and actionable" -- no literal ordering rule is specified in any
    approved document, the same class of gap `catalog.application.duplicate_detection_service`'s
    own docstring names and resolves for FR-ADV-009). This task's own defensible choice:
    oldest-first (FIFO) -- the case that has waited longest for review surfaces first, mirroring
    `profiles.domain.policies.order_queue`'s own "earliest deadline first" reasoning for its
    SLA-bound queue (moderation cases carry no SLA field of their own in the documented physical
    schema, so `created_at` is the only ordering signal available)."""
    return sorted(cases, key=lambda case: case.created_at)


POST_PUBLICATION_MODERATION = True
"""`PostPublicationPolicy [P]` (BRULE-17/DEC-14): "content is visible on publication and reviewed
afterwards, unless automated validation rules flag it first." This is not a runtime predicate
this module evaluates -- publication and visibility are catalog's own domain (`catalog.domain.
listing.Listing.is_publicly_visible`, `PublicationPolicy [P]`, `I-06`); moderation has no
mechanism to gate publication even if it wanted to (no static import of catalog, `docs/adr/
0003-...md`'s own scope confirms moderation only ever *reacts* to already-published/already-
flagged content). This constant exists as the one place the policy's own [P]-fixed, "never
introduce a pre-publication gate" constraint is documented and asserted by
`test_post_publication_policy.py`, so a future change that tried to add one would have an
obvious, named thing to update (and, per the invariant, should not)."""
