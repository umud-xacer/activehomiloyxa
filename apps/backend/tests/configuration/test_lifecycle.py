"""The generic version lifecycle state machine (Config Framework Sec 10; DDD I-07) -- shared by
all eight entities, so one test file proves it for all of them."""

from __future__ import annotations

import pytest

from configuration.domain.lifecycle import (
    HeadStatus,
    IllegalLifecycleTransitionError,
    VersionStatus,
    assert_legal_version_transition,
)

LEGAL = [
    (VersionStatus.DRAFT, VersionStatus.VALIDATION),
    (VersionStatus.VALIDATION, VersionStatus.APPROVAL),
    (VersionStatus.VALIDATION, VersionStatus.PUBLISHED),
    (VersionStatus.VALIDATION, VersionStatus.DRAFT),
    (VersionStatus.APPROVAL, VersionStatus.PUBLISHED),
    (VersionStatus.APPROVAL, VersionStatus.DRAFT),
    (VersionStatus.PUBLISHED, VersionStatus.DEPRECATED),
    (VersionStatus.PUBLISHED, VersionStatus.ARCHIVED),
    (VersionStatus.DEPRECATED, VersionStatus.ARCHIVED),
]

ILLEGAL = [
    (VersionStatus.DRAFT, VersionStatus.PUBLISHED),
    (VersionStatus.DRAFT, VersionStatus.APPROVAL),
    (VersionStatus.DRAFT, VersionStatus.DEPRECATED),
    (VersionStatus.PUBLISHED, VersionStatus.DRAFT),
    (VersionStatus.PUBLISHED, VersionStatus.VALIDATION),
    (VersionStatus.ARCHIVED, VersionStatus.PUBLISHED),
    (VersionStatus.ARCHIVED, VersionStatus.DRAFT),
    (VersionStatus.DEPRECATED, VersionStatus.PUBLISHED),
]


@pytest.mark.parametrize("from_status,to_status", LEGAL)
def test_I07_legal_version_transition_allowed(
    from_status: VersionStatus, to_status: VersionStatus
) -> None:
    assert_legal_version_transition(from_status, to_status)


@pytest.mark.parametrize("from_status,to_status", ILLEGAL)
def test_I07_illegal_version_transition_refused(
    from_status: VersionStatus, to_status: VersionStatus
) -> None:
    with pytest.raises(IllegalLifecycleTransitionError) as exc_info:
        assert_legal_version_transition(from_status, to_status)
    assert exc_info.value.from_status == from_status.value
    assert exc_info.value.to_status == to_status.value


def test_version_status_exact_member_set() -> None:
    assert {s.value for s in VersionStatus} == {
        "DRAFT",
        "VALIDATION",
        "APPROVAL",
        "PUBLISHED",
        "DEPRECATED",
        "ARCHIVED",
    }


def test_head_status_exact_member_set() -> None:
    assert {s.value for s in HeadStatus} == {
        "DRAFT",
        "PUBLISHED",
        "DEPRECATED",
        "ARCHIVED",
    }
