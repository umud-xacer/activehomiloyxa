"""The version lifecycle state machine (Config Framework Sec 10; Physical DB Sec 2.4 CHECK
constraints; DDD I-07). One state machine, shared by all eight entities -- the generic
Head+Version machinery this whole module is built around (DB Architecture Sec 18 "build the
Head + Version + snapshot + publish-transaction machinery generically ... instantiate it per
entity; do not hand-roll eight variants").
"""

from __future__ import annotations

from enum import StrEnum


class VersionStatus(StrEnum):
    """Physical DB Sec 2.4 `<entity>_version.status` CHECK constraint, exact member set."""

    DRAFT = "DRAFT"
    VALIDATION = "VALIDATION"
    APPROVAL = "APPROVAL"
    PUBLISHED = "PUBLISHED"
    DEPRECATED = "DEPRECATED"
    ARCHIVED = "ARCHIVED"


class HeadStatus(StrEnum):
    """Physical DB Sec 2.4 `<entity>.status` CHECK constraint (head-level lifecycle), exact
    member set."""

    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    DEPRECATED = "DEPRECATED"
    ARCHIVED = "ARCHIVED"


class IllegalLifecycleTransitionError(ValueError):
    """Raised when a version/head transition is attempted outside the fixed lifecycle graph
    (Config Framework Sec 10)."""

    def __init__(self, from_status: str, to_status: str, entity: str) -> None:
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(f"{entity}: illegal transition {from_status} -> {to_status}")


# Config Framework Sec 10 diagram: Draft -> Validation -> Approval (controlled only) ->
# Published -> Deprecated -> Archived, plus the two gate-failure returns to Draft and the one
# guard-trigger-permitted post-publish mutation (Published -> Deprecated/Archived, Physical DB
# Sec 2.4 "Immutability").
_LEGAL_VERSION_TRANSITIONS: dict[VersionStatus, frozenset[VersionStatus]] = {
    VersionStatus.DRAFT: frozenset({VersionStatus.VALIDATION}),
    VersionStatus.VALIDATION: frozenset(
        {VersionStatus.APPROVAL, VersionStatus.PUBLISHED, VersionStatus.DRAFT}
    ),
    VersionStatus.APPROVAL: frozenset({VersionStatus.PUBLISHED, VersionStatus.DRAFT}),
    VersionStatus.PUBLISHED: frozenset({VersionStatus.DEPRECATED, VersionStatus.ARCHIVED}),
    VersionStatus.DEPRECATED: frozenset({VersionStatus.ARCHIVED}),
    VersionStatus.ARCHIVED: frozenset(),
}


def assert_legal_version_transition(
    from_status: VersionStatus, to_status: VersionStatus, *, entity: str = "ConfigVersion"
) -> None:
    if to_status not in _LEGAL_VERSION_TRANSITIONS.get(from_status, frozenset()):
        raise IllegalLifecycleTransitionError(from_status.value, to_status.value, entity)
