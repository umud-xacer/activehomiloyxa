"""Unit tests for `AuditEntry` (DDD Sec 5.13, FR-AUDIT-001, I-22)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from analytics.domain import AuditEntry, ImmutableFactMutationError
from shared_kernel import UserId

_NOW = datetime(2026, 7, 13, tzinfo=UTC)


def _make_entry(**overrides: object) -> AuditEntry:
    defaults: dict[str, object] = {
        "action": "ModerationActionTaken",
        "actor_user_id": UserId(value=uuid4()),
        "actor_context": None,
        "target_type": "Listing",
        "target_id": uuid4(),
        "payload": {"moderationCaseId": str(uuid4())},
        "source_event_id": uuid4(),
        "occurred_at": _NOW,
    }
    defaults.update(overrides)
    return AuditEntry.create(**defaults)  # type: ignore[arg-type]


def test_create_populates_every_field() -> None:
    actor = UserId(value=uuid4())
    entry = _make_entry(actor_user_id=actor, action="PaymentConfirmed")
    assert entry.action == "PaymentConfirmed"
    assert entry.actor_user_id == actor
    assert entry.occurred_at == _NOW


def test_create_accepts_a_null_actor() -> None:
    """A system-triggered action (e.g. a config publish with no human actor) is valid."""
    entry = _make_entry(actor_user_id=None)
    assert entry.actor_user_id is None


# I-22: an AuditEntry is an immutable fact -- attempted mutation is rejected at the domain level.
def test_I22_attribute_assignment_is_rejected() -> None:
    entry = _make_entry()
    with pytest.raises(ImmutableFactMutationError):
        entry.action = "SomethingElse"


def test_I22_attribute_deletion_is_rejected() -> None:
    entry = _make_entry()
    with pytest.raises(ImmutableFactMutationError):
        del entry.action


def test_I22_payload_field_itself_cannot_be_reassigned() -> None:
    entry = _make_entry(payload={"a": 1})
    with pytest.raises(ImmutableFactMutationError):
        entry.payload = {"a": 2}
