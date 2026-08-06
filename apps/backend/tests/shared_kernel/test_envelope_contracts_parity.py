"""Proves shared_kernel.EventEnvelope and contracts/events/'s catalogue are structurally
identical -- not a coincidence to maintain by hand, but guaranteed by construction (every event
in the catalogue is a direct subclass of EventEnvelope), verified here field-for-field per the
P-02 checklist ("construct each from both definitions and confirm field-for-field parity")."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from contracts.events import EVENT_CATALOGUE, UserRegistered
from shared_kernel import EventEnvelope

DDD_SEC_5_14_ENVELOPE_FIELDS = {
    "event_id",  # event id
    "event_type",  # event type
    "occurred_at",  # occurred-at
    "actor",  # actor
    "aggregate_type",
    "aggregate_id",  # aggregate reference
    "aggregate_version",  # version
    "payload",
}


def test_shared_kernel_envelope_matches_ddd_sec_5_14_exactly() -> None:
    assert set(EventEnvelope.model_fields.keys()) == DDD_SEC_5_14_ENVELOPE_FIELDS


def test_every_catalogue_event_is_a_true_subclass_of_the_shared_kernel_envelope() -> None:
    for cls in EVENT_CATALOGUE.values():
        assert issubclass(cls, EventEnvelope)


def test_constructing_from_both_definitions_yields_field_for_field_parity() -> None:
    """Build one instance directly from `shared_kernel.EventEnvelope` and one from a
    `contracts.events` class with the same envelope data, and confirm every shared field
    matches."""
    event_id = uuid4()
    occurred_at = datetime.now(UTC)
    actor = uuid4()
    aggregate_type = "UserAccount"
    aggregate_id = uuid4()
    aggregate_version = 1
    payload = {"userId": "abc-123"}

    from_shared_kernel = EventEnvelope(
        event_type="UserRegistered",
        event_id=event_id,
        occurred_at=occurred_at,
        actor=actor,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        aggregate_version=aggregate_version,
        payload=payload,
    )
    from_contracts = UserRegistered(
        event_id=event_id,
        occurred_at=occurred_at,
        actor=actor,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        aggregate_version=aggregate_version,
        payload=payload,
    )

    for field_name in DDD_SEC_5_14_ENVELOPE_FIELDS:
        assert getattr(from_shared_kernel, field_name) == getattr(from_contracts, field_name), (
            f"envelope field {field_name!r} diverges between shared_kernel and contracts"
        )
