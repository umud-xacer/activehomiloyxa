"""configuration/domain -- the generic Head+Version machinery, WhitelistRegistry, pre-activation
gate, and the eight entity content models (Task P-04). Imports `shared_kernel` only (Clean
Architecture rule 1); never imported by another module (`domain/` is never part of a module's
public surface, AIR-02)."""

from __future__ import annotations

from configuration.domain.entity_types import (
    CONTROLLED_TRACK_ENTITIES,
    SUPER_ADMIN_APPROVAL_ENTITIES,
    TABLE_NAME_BY_ENTITY_TYPE,
    AuthoringTrack,
    ConfigEntityType,
    authoring_track,
    requires_super_admin_approval,
)
from configuration.domain.events import resolve_configuration_changed_event_type
from configuration.domain.exceptions import (
    ApproverPermissionError,
    DraftRequiredError,
    DuplicateCodeError,
    SelfApprovalError,
)
from configuration.domain.gate import GateContext, GateError, GateResult, PreActivationGate
from configuration.domain.head_version import ConfigHead, ConfigVersion
from configuration.domain.lifecycle import (
    HeadStatus,
    IllegalLifecycleTransitionError,
    VersionStatus,
    assert_legal_version_transition,
)
from configuration.domain.permissions import flatten_role_permissions
from configuration.domain.taxonomy import creates_cycle, would_orphan_listings
from configuration.domain.whitelist import WhitelistRegistry, WhitelistViolationError

__all__ = [
    "CONTROLLED_TRACK_ENTITIES",
    "SUPER_ADMIN_APPROVAL_ENTITIES",
    "TABLE_NAME_BY_ENTITY_TYPE",
    "ApproverPermissionError",
    "AuthoringTrack",
    "ConfigEntityType",
    "ConfigHead",
    "ConfigVersion",
    "DraftRequiredError",
    "DuplicateCodeError",
    "GateContext",
    "GateError",
    "GateResult",
    "HeadStatus",
    "IllegalLifecycleTransitionError",
    "PreActivationGate",
    "SelfApprovalError",
    "VersionStatus",
    "WhitelistRegistry",
    "WhitelistViolationError",
    "assert_legal_version_transition",
    "authoring_track",
    "creates_cycle",
    "flatten_role_permissions",
    "requires_super_admin_approval",
    "resolve_configuration_changed_event_type",
    "would_orphan_listings",
]
