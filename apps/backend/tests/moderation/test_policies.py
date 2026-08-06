"""Tests for `moderation.domain.policies` (Task P-12): `QueueOrderingPolicy` (FIFO, oldest-first)
and the `PostPublicationPolicy [P]` constant assertion (BRULE-17/DEC-14).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from moderation.domain import (
    POST_PUBLICATION_MODERATION,
    Subject,
    SubjectType,
    order_queue,
)
from moderation.domain.moderation_case import ModerationCase

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


def _case(created_at: datetime) -> ModerationCase:
    return ModerationCase.open_from_report(
        case_id=uuid4(),
        subject=Subject(subject_type=SubjectType.LISTING, subject_id=uuid4()),
        reporter_user_id=uuid4(),
        reason="spam",
        now=created_at,
    )


def test_order_queue_is_oldest_first() -> None:
    newest = _case(NOW)
    oldest = _case(NOW - timedelta(hours=5))
    middle = _case(NOW - timedelta(hours=2))
    ordered = order_queue([newest, middle, oldest])
    assert [c.id for c in ordered] == [oldest.id, middle.id, newest.id]


def test_order_queue_empty_list() -> None:
    assert order_queue([]) == []


def test_post_publication_policy_never_gates_publication() -> None:
    """BRULE-17/DEC-14: "content is visible on publication and reviewed afterwards" -- moderation
    never introduces a pre-publication gate. Asserted here so a future change flipping this
    constant has an obvious, named thing to update (and, per the invariant, should not)."""
    assert POST_PUBLICATION_MODERATION is True
