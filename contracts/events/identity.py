"""identity (BC-01) domain events -- DDD Sec 6, the authoritative v1 event catalogue.

STATUS: frozen (Task P-01). Schema only: each class is the shared envelope
(`shared_kernel.EventEnvelope`) with `event_type` pinned to its own past-tense name. No
publishing logic, no handlers -- that is outbox/adapter work for a later task. Do not add an
event here that is not a row in DDD Sec 6 for this context; do not remove one either without an
ADR (Playbook Sec 18) amending the Domain Model.
"""

from __future__ import annotations

from typing import Literal

from shared_kernel import EventEnvelope


class UserRegistered(EventEnvelope):
    """Emitted when: Account created via any method.

    Principal consumers: Notifications, Analytics.
    """

    event_type: Literal["UserRegistered"] = "UserRegistered"


class AccountSuspended(EventEnvelope):
    """Emitted when: Operator suspension.

    Principal consumers: Catalog (hide listings), Messaging, Notifications, Audit.
    """

    event_type: Literal["AccountSuspended"] = "AccountSuspended"


class AccountClosed(EventEnvelope):
    """Emitted when: User closure.

    Principal consumers: Catalog (hide listings), Messaging, Notifications, Audit.
    """

    event_type: Literal["AccountClosed"] = "AccountClosed"


class RegistrationApproved(EventEnvelope):
    """ADR-0007. Emitted when: a reviewer approves a PENDING account's signup anketa.

    Principal consumers: Notifications (unlock-workspace email/push).
    """

    event_type: Literal["RegistrationApproved"] = "RegistrationApproved"


class RegistrationRejected(EventEnvelope):
    """ADR-0007. Emitted when: a reviewer rejects a PENDING account's signup anketa.

    Principal consumers: Notifications (rejection-reason email/push).
    """

    event_type: Literal["RegistrationRejected"] = "RegistrationRejected"
