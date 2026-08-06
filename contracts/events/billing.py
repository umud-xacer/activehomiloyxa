"""billing (BC-08) domain events -- DDD Sec 6, the authoritative v1 event catalogue.

STATUS: frozen (Task P-01). Schema only: each class is the shared envelope
(`shared_kernel.EventEnvelope`) with `event_type` pinned to its own past-tense name. No
publishing logic, no handlers -- that is outbox/adapter work for a later task. Do not add an
event here that is not a row in DDD Sec 6 for this context; do not remove one either without an
ADR (Playbook Sec 18) amending the Domain Model.
"""

from __future__ import annotations

from typing import Literal

from shared_kernel import EventEnvelope


class OrderPlaced(EventEnvelope):
    """Emitted when: Purchase requested.

    Principal consumers: Administration (billing queue), Notifications.
    """

    event_type: Literal["OrderPlaced"] = "OrderPlaced"


class InvoiceIssued(EventEnvelope):
    """Emitted when: Invoice generated.

    Principal consumers: Notifications.
    """

    event_type: Literal["InvoiceIssued"] = "InvoiceIssued"


class PaymentConfirmed(EventEnvelope):
    """Emitted when: Operator confirms offline payment.

    Principal consumers: Audit, Notifications.
    """

    event_type: Literal["PaymentConfirmed"] = "PaymentConfirmed"


class EntitlementActivated(EventEnvelope):
    """Emitted when: Entitlement becomes active.

    Principal consumers: Catalog (promotion/quota), Profiles (verification eligibility), Ad-Serving (booking), Analytics.
    """

    event_type: Literal["EntitlementActivated"] = "EntitlementActivated"


class EntitlementExpired(EventEnvelope):
    """Emitted when: Term end.

    Principal consumers: Same consumers (benefit withdrawal), Notifications.
    """

    event_type: Literal["EntitlementExpired"] = "EntitlementExpired"


class EntitlementRevoked(EventEnvelope):
    """Emitted when: Revocation.

    Principal consumers: Same consumers (benefit withdrawal), Notifications.
    """

    event_type: Literal["EntitlementRevoked"] = "EntitlementRevoked"
