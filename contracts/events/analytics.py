"""analytics (BC-13) domain events -- DDD Sec 6, the authoritative v1 event catalogue.

STATUS: frozen (Task P-01). Schema only: each class is the shared envelope
(`shared_kernel.EventEnvelope`) with `event_type` pinned to its own past-tense name. No
publishing logic, no handlers -- that is outbox/adapter work for a later task. Do not add an
event here that is not a row in DDD Sec 6 for this context; do not remove one either without an
ADR (Playbook Sec 18) amending the Domain Model.
"""

from __future__ import annotations

from typing import Literal

from shared_kernel import EventEnvelope


class MetricEventCaptured(EventEnvelope):
    """Emitted when: On ingestion (sink).

    Principal consumers: Reports/statistics projections.
    """

    event_type: Literal["MetricEventCaptured"] = "MetricEventCaptured"


class AuditEntryRecorded(EventEnvelope):
    """Emitted when: On ingestion (sink).

    Principal consumers: Reports/statistics projections.
    """

    event_type: Literal["AuditEntryRecorded"] = "AuditEntryRecorded"
