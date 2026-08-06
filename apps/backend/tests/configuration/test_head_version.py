"""The generic Head+Version aggregate (DDD I-07; Config Framework Sec 2.4-2.6)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from configuration.domain.entity_types import AuthoringTrack, ConfigEntityType
from configuration.domain.exceptions import DraftRequiredError, SelfApprovalError
from configuration.domain.head_version import ConfigHead, ConfigVersion
from configuration.domain.lifecycle import (
    HeadStatus,
    IllegalLifecycleTransitionError,
    VersionStatus,
)


def _version(**overrides: object) -> ConfigVersion:
    now = datetime.now(UTC)
    author = uuid4()
    defaults: dict[str, object] = {
        "id": uuid4(),
        "head_id": uuid4(),
        "version_number": 1,
        "status": VersionStatus.DRAFT,
        "definition_document": {"k": "v"},
        "snapshot_document": None,
        "validity_from": None,
        "validity_until": None,
        "rollback_of_version_id": None,
        "approved_by": None,
        "approved_at": None,
        "published_by": None,
        "published_at": None,
        "created_at": now,
        "created_by": author,
    }
    defaults.update(overrides)
    return ConfigVersion(**defaults)  # type: ignore[arg-type]


def _head(entity_type: ConfigEntityType, **overrides: object) -> ConfigHead:
    now = datetime.now(UTC)
    actor = uuid4()
    defaults: dict[str, object] = {
        "id": uuid4(),
        "entity_type": entity_type,
        "code": "demo",
        "current_version_id": None,
        "status": HeadStatus.DRAFT,
        "business_owner": "Product Owner",
        "created_at": now,
        "created_by": actor,
        "updated_at": now,
        "updated_by": actor,
    }
    defaults.update(overrides)
    return ConfigHead(**defaults)  # type: ignore[arg-type]


def test_edit_draft_on_draft_version_succeeds() -> None:
    version = _version(status=VersionStatus.DRAFT)
    edited = version.edit_draft(definition_document={"k": "v2"})
    assert edited.definition_document == {"k": "v2"}
    assert version.definition_document == {"k": "v"}  # immutable: original untouched


def test_edit_draft_on_non_draft_version_refused() -> None:
    version = _version(status=VersionStatus.PUBLISHED)
    with pytest.raises(DraftRequiredError):
        version.edit_draft(definition_document={"k": "v2"})


def test_move_to_validation_then_awaiting_approval() -> None:
    version = _version(status=VersionStatus.DRAFT).move_to_validation()
    assert version.status is VersionStatus.VALIDATION
    version = version.move_to_awaiting_approval()
    assert version.status is VersionStatus.APPROVAL


def test_return_to_draft_after_failed_gate() -> None:
    version = _version(status=VersionStatus.VALIDATION).return_to_draft_after_failed_gate()
    assert version.status is VersionStatus.DRAFT


def test_publish_directly_stamps_publisher_and_snapshot() -> None:
    now = datetime.now(UTC)
    publisher = uuid4()
    version = _version(status=VersionStatus.VALIDATION).publish_directly(
        now=now, publisher_id=publisher, snapshot_document={"resolved": True}
    )
    assert version.status is VersionStatus.PUBLISHED
    assert version.published_by == publisher
    assert version.published_at == now
    assert version.snapshot_document == {"resolved": True}
    assert version.approved_by is None  # standard track: no checker


def test_approve_and_publish_stamps_checker_and_publisher_identically() -> None:
    now = datetime.now(UTC)
    author = uuid4()
    checker = uuid4()
    version = _version(status=VersionStatus.APPROVAL, created_by=author).approve_and_publish(
        now=now,
        checker_id=checker,
        approval_note="looks good",
        snapshot_document={"r": 1},
    )
    assert version.status is VersionStatus.PUBLISHED
    assert version.approved_by == checker
    assert version.published_by == checker
    assert version.approved_at == now == version.published_at


def test_I16_self_approval_refused() -> None:
    """Config Framework Sec 2.3: "the approver must be a different principal" -- I-16's
    maker-checker discipline is what keeps configuration bounded to a controlled process, not
    just a whitelist check."""
    author = uuid4()
    version = _version(status=VersionStatus.APPROVAL, created_by=author)
    with pytest.raises(SelfApprovalError):
        version.approve_and_publish(
            now=datetime.now(UTC),
            checker_id=author,
            approval_note=None,
            snapshot_document={},
        )


def test_deprecate_and_archive_are_the_only_post_publish_moves() -> None:
    published = _version(status=VersionStatus.PUBLISHED)
    assert published.deprecate().status is VersionStatus.DEPRECATED
    assert published.archive().status is VersionStatus.ARCHIVED
    with pytest.raises(IllegalLifecycleTransitionError):
        published.with_status(VersionStatus.DRAFT)


def test_is_current_candidate_only_true_when_published() -> None:
    assert not _version(status=VersionStatus.DRAFT).is_current_candidate()
    assert not _version(status=VersionStatus.APPROVAL).is_current_candidate()
    assert _version(status=VersionStatus.PUBLISHED).is_current_candidate()


@pytest.mark.parametrize(
    "entity_type,expected_track",
    [
        (ConfigEntityType.CATEGORY, AuthoringTrack.CONTROLLED),
        (ConfigEntityType.FORM_DEFINITION, AuthoringTrack.CONTROLLED),
        (ConfigEntityType.PRODUCT_DEFINITION, AuthoringTrack.CONTROLLED),
        (ConfigEntityType.PLACEMENT_SLOT, AuthoringTrack.CONTROLLED),
        (ConfigEntityType.ROLE_DEFINITION, AuthoringTrack.CONTROLLED),
        (ConfigEntityType.PLATFORM_SETTINGS, AuthoringTrack.CONTROLLED),
        (ConfigEntityType.SEARCH_CONFIGURATION, AuthoringTrack.STANDARD),
        (ConfigEntityType.NOTIFICATION_TEMPLATE, AuthoringTrack.STANDARD),
    ],
)
def test_head_authoring_track_matches_entity_type(
    entity_type: ConfigEntityType, expected_track: AuthoringTrack
) -> None:
    assert _head(entity_type).authoring_track is expected_track


@pytest.mark.parametrize(
    "entity_type,expected",
    [
        (ConfigEntityType.ROLE_DEFINITION, True),
        (ConfigEntityType.PLATFORM_SETTINGS, True),
        (ConfigEntityType.CATEGORY, False),
        (ConfigEntityType.FORM_DEFINITION, False),
    ],
)
def test_head_requires_super_admin_approval(entity_type: ConfigEntityType, expected: bool) -> None:
    assert _head(entity_type).requires_super_admin_approval is expected


def test_move_current_version_updates_pointer_and_status() -> None:
    head = _head(ConfigEntityType.SEARCH_CONFIGURATION, status=HeadStatus.DRAFT)
    now = datetime.now(UTC)
    actor = uuid4()
    version_id = uuid4()
    updated = head.move_current_version(version_id, now=now, actor_id=actor)
    assert updated.current_version_id == version_id
    assert updated.status is HeadStatus.PUBLISHED
    assert updated.updated_at == now
    assert updated.updated_by == actor
    assert head.current_version_id is None  # immutable: original untouched
