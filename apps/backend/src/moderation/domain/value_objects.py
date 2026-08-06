"""moderation -- value objects (DDD Sec 5.11 BC-11). Persistence-ignorant, mirrors
`profiles.domain.value_objects`'s style.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class SubjectType(StrEnum):
    """DDD Sec 5.11 VO `Subject` -- the closed set of what a `ModerationCase` may be opened
    about. `PROFILE` is not in the original DDD Sec 5.11 table; added by
    `docs/adr/0003-moderation-profile-target-extension.md` (Task P-12) so a case can reference a
    `BusinessProfile` for badge-revocation/profile-archival actions."""

    LISTING = "LISTING"
    CONVERSATION = "CONVERSATION"
    USER = "USER"
    PROFILE = "PROFILE"


class OriginType(StrEnum):
    """DDD Sec 5.11 VO `Origin` -- how a case entered the queue."""

    USER_REPORT = "USER_REPORT"
    AUTOMATED_FLAG = "AUTOMATED_FLAG"


class CaseStatus(StrEnum):
    """DDD Sec 5.11 VO `CaseStatus` -- `Open -> InReview -> Resolved`."""

    OPEN = "OPEN"
    IN_REVIEW = "IN_REVIEW"
    RESOLVED = "RESOLVED"


TERMINAL_CASE_STATUSES = frozenset({CaseStatus.RESOLVED})


class ResolutionAction(StrEnum):
    """DDD Sec 5.11 VO `ResolutionAction [P]` -- the closed verb set (BR-MOD-02), extended by
    `docs/adr/0003-moderation-profile-target-extension.md` with `REVOKE_BADGE`/`ARCHIVE_PROFILE`.
    `[P]` per DDD's own marker convention: fixed, changeable only by release + ADR, never by
    configuration -- this enum is the one and only place this vocabulary is defined."""

    HIDE = "HIDE"
    REJECT = "REJECT"
    SUSPEND = "SUSPEND"
    REQUEST_CORRECTION = "REQUEST_CORRECTION"
    REMOVE = "REMOVE"
    SUSPEND_ACCOUNT = "SUSPEND_ACCOUNT"
    DISMISS = "DISMISS"
    REVOKE_BADGE = "REVOKE_BADGE"
    ARCHIVE_PROFILE = "ARCHIVE_PROFILE"


LISTING_ACTIONS = frozenset(
    {
        ResolutionAction.HIDE,
        ResolutionAction.REJECT,
        ResolutionAction.SUSPEND,
        ResolutionAction.REQUEST_CORRECTION,
        ResolutionAction.REMOVE,
        ResolutionAction.DISMISS,
    }
)
USER_ACTIONS = frozenset(
    {
        ResolutionAction.SUSPEND_ACCOUNT,
        ResolutionAction.REQUEST_CORRECTION,
        ResolutionAction.DISMISS,
    }
)
PROFILE_ACTIONS = frozenset(
    {
        ResolutionAction.REVOKE_BADGE,
        ResolutionAction.ARCHIVE_PROFILE,
        ResolutionAction.REQUEST_CORRECTION,
        ResolutionAction.DISMISS,
    }
)
CONVERSATION_ACTIONS = frozenset(
    {
        ResolutionAction.SUSPEND_ACCOUNT,
        ResolutionAction.REQUEST_CORRECTION,
        ResolutionAction.DISMISS,
    }
)
"""No document names a conversation-directed catalog/identity/profiles command beyond suspending
the offending user's account -- messaging is not a command target in this task's scope (P-12's
own Dependencies list only identity/catalog/profiles/configuration), so a `CONVERSATION`-subject
case can request correction, suspend the reported user's account, or be dismissed, but never a
listing- or profile-specific verb."""

ACTIONS_BY_SUBJECT_TYPE: dict[SubjectType, frozenset[ResolutionAction]] = {
    SubjectType.LISTING: LISTING_ACTIONS,
    SubjectType.USER: USER_ACTIONS,
    SubjectType.PROFILE: PROFILE_ACTIONS,
    SubjectType.CONVERSATION: CONVERSATION_ACTIONS,
}
"""Which `ResolutionAction`s are semantically valid for which `SubjectType` -- e.g. `SUSPEND_
ACCOUNT` needs a `UserRef` to suspend, so applying it to a `LISTING`-subject case is a caller
bug, not a legal decision (`Listing` has no account to suspend). Not itself a DDD-documented
table; a direct, necessary consequence of "each verb maps to exactly one target/transition"
(see `catalog.interfaces.moderation_port`'s own docstring) -- enforced by `ModerationCase.
resolve` via `InvalidResolutionForSubjectError`."""


@dataclass(frozen=True)
class Subject:
    """DDD Sec 5.11 VO `Subject (ListingRef / ConversationRef / UserRef` -- extended with
    `ProfileRef` by ADR-0003`)`. `subject_id` is an IDENTIFIER only -- never an imported object
    from the owning module (AIR-01/SAD Sec 8.1: moderation may statically import `shared_kernel`
    only)."""

    subject_type: SubjectType
    subject_id: UUID


@dataclass(frozen=True)
class Origin:
    """DDD Sec 5.11 VO `Origin (UserReport with reason, or AutomatedFlag with rule key)`.
    Constructed only via `Origin.from_report`/`Origin.from_flag` -- mirrors `ck_origin_shape`
    ((origin_type='USER_REPORT') = (report_reason IS NOT NULL)) as a structural guarantee rather
    than a runtime check re-derived elsewhere."""

    origin_type: OriginType
    report_reason: str | None
    rule_key: str | None

    @staticmethod
    def from_report(reason: str) -> Origin:
        return Origin(origin_type=OriginType.USER_REPORT, report_reason=reason, rule_key=None)

    @staticmethod
    def from_flag(rule_key: str) -> Origin:
        return Origin(origin_type=OriginType.AUTOMATED_FLAG, report_reason=None, rule_key=rule_key)


@dataclass(frozen=True)
class Resolution:
    """The recorded decision (FR-MOD-003/004) -- constructed only by `ModerationCase.resolve`."""

    action: ResolutionAction
    note: str | None
    moderator_user_id: UUID
    resolved_at: datetime
