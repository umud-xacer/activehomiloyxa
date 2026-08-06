"""The generic Head+Version aggregate (DDD I-07; Config Framework Sec 2.4-2.6, Sec 10; Physical
DB Sec 2.4). One implementation, instantiated for all eight entity types via `entity_type`/
`code` rather than eight hand-rolled aggregate classes (DB Architecture Sec 18).

Persistence-ignorant (DB Architecture Sec 18 "domain objects are persistence-ignorant"): these
are plain domain objects: state transitions happen here, guarded by the lifecycle graph
(`lifecycle.py`) and the maker-checker rule, and the repository (`infrastructure/`) persists the
result plus the outbox event in the same transaction. `ConfigHead`/`ConfigVersion` never import
SQLAlchemy, Redis, or FastAPI.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any
from uuid import UUID

from configuration.domain.entity_types import (
    AuthoringTrack,
    ConfigEntityType,
    authoring_track,
    requires_super_admin_approval,
)
from configuration.domain.exceptions import DraftRequiredError, SelfApprovalError
from configuration.domain.lifecycle import (
    HeadStatus,
    VersionStatus,
    assert_legal_version_transition,
)


@dataclass(frozen=True)
class ConfigVersion:
    """`configuration.<entity>_version` (Physical DB Sec 2.4). Immutable once PUBLISHED (PD-07
    guard trigger permits exactly one further mutation: PUBLISHED -> DEPRECATED/ARCHIVED)."""

    id: UUID
    head_id: UUID
    version_number: int
    status: VersionStatus
    definition_document: dict[str, Any]
    snapshot_document: dict[str, Any] | None
    validity_from: datetime | None
    validity_until: datetime | None
    rollback_of_version_id: UUID | None
    approved_by: UUID | None
    approved_at: datetime | None
    published_by: UUID | None
    published_at: datetime | None
    created_at: datetime
    created_by: UUID

    def with_status(
        self, new_status: VersionStatus, *, entity: str = "ConfigVersion"
    ) -> ConfigVersion:
        assert_legal_version_transition(self.status, new_status, entity=entity)
        return replace(self, status=new_status)

    def edit_draft(self, *, definition_document: dict[str, Any]) -> ConfigVersion:
        if self.status != VersionStatus.DRAFT:
            raise DraftRequiredError(str(self.id), self.status.value)
        return replace(self, definition_document=definition_document)

    def move_to_validation(self) -> ConfigVersion:
        return self.with_status(VersionStatus.VALIDATION)

    def return_to_draft_after_failed_gate(self) -> ConfigVersion:
        return self.with_status(VersionStatus.DRAFT)

    def move_to_awaiting_approval(self) -> ConfigVersion:
        """Config Framework Sec 2.3/2.4: the maker's publish call, for a controlled-track
        entity, submits for approval rather than publishing directly."""
        return self.with_status(VersionStatus.APPROVAL)

    def approve_and_publish(
        self,
        *,
        now: datetime,
        checker_id: UUID,
        approval_note: str | None,
        snapshot_document: dict[str, Any],
    ) -> ConfigVersion:
        """The checker's publish call on a version already in APPROVAL. `approval_note` is
        recorded but not persisted as a separate column (Physical DB Sec 2.4 has no such column
        -- OpenAPI's `ConfigPublishRequest.approvalNote` is captured in the audit trail/outbox
        event payload instead, by the calling use case)."""
        if self.created_by == checker_id:
            raise SelfApprovalError()
        version = self.with_status(VersionStatus.PUBLISHED)
        return replace(
            version,
            approved_by=checker_id,
            approved_at=now,
            published_by=checker_id,
            published_at=now,
            snapshot_document=snapshot_document,
        )

    def publish_directly(
        self, *, now: datetime, publisher_id: UUID, snapshot_document: dict[str, Any]
    ) -> ConfigVersion:
        """Standard-track publish: one call, VALIDATION -> PUBLISHED, no checker required."""
        version = self.with_status(VersionStatus.PUBLISHED)
        return replace(
            version,
            published_by=publisher_id,
            published_at=now,
            snapshot_document=snapshot_document,
        )

    def deprecate(self) -> ConfigVersion:
        return self.with_status(VersionStatus.DEPRECATED)

    def archive(self) -> ConfigVersion:
        return self.with_status(VersionStatus.ARCHIVED)

    def is_current_candidate(self) -> bool:
        return self.status == VersionStatus.PUBLISHED


@dataclass(frozen=True)
class ConfigHead:
    """`configuration.<entity>` (Physical DB Sec 2.4). One row per authored entity instance
    (e.g. one Category, one RoleDefinition); `current_version_id` is the deferrable pointer
    resolved within the same publish transaction as the new version's insert."""

    id: UUID
    entity_type: ConfigEntityType
    code: str
    current_version_id: UUID | None
    status: HeadStatus
    business_owner: str
    created_at: datetime
    created_by: UUID
    updated_at: datetime
    updated_by: UUID
    lock_version: int = 0

    @property
    def authoring_track(self) -> AuthoringTrack:
        return authoring_track(self.entity_type)

    @property
    def requires_super_admin_approval(self) -> bool:
        return requires_super_admin_approval(self.entity_type)

    def move_current_version(
        self, version_id: UUID, *, now: datetime, actor_id: UUID
    ) -> ConfigHead:
        return replace(
            self,
            current_version_id=version_id,
            status=HeadStatus.PUBLISHED,
            updated_at=now,
            updated_by=actor_id,
        )
