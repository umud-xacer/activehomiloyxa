"""notifications -- typed domain exceptions, one per invariant violated (Playbook Sec 6). Mirrors
`moderation.domain.exceptions`'s style. `interfaces/errors.py` maps each of these to a
`contracts.errors.Problem` (closed `ErrorCode` vocabulary).
"""

from __future__ import annotations


class NotificationDomainError(Exception):
    """Base for every typed exception raised by notifications' domain/ layer."""


class IllegalNotificationStateTransitionError(NotificationDomainError):
    """`mark_sent`/`mark_failed` are legal only from `QUEUED` -- a delivery attempt is recorded
    exactly once; retries are a new dispatch attempt on the SAME row's `attempts` counter, never a
    second transition from an already-terminal delivery status."""

    def __init__(self, transition: str, current: str) -> None:
        self.transition = transition
        self.current = current
        super().__init__(f"cannot {transition} a notification in delivery status {current}")


class UnsupportedChannelError(NotificationDomainError):
    """A configuration-authored template's own `channel` string is not one of the fixed
    `Channel` values -- defence in depth: `configuration`'s own `WhitelistRegistry.
    check_notification_channel` already rejects this at authoring time (I-16), so this only
    fires if a snapshot somehow diverges from that whitelist gate."""

    def __init__(self, channel: str) -> None:
        self.channel = channel
        super().__init__(f"unsupported notification channel: {channel!r}")
