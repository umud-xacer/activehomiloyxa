"""Typed domain exceptions named for the invariant/check they protect (Playbook Sec 4). See also
`whitelist.WhitelistViolationError` (I-16) and `lifecycle.IllegalLifecycleTransitionError`.

Config Framework Sec 9's other named check categories ("Missing dependencies", "Circular
references", I-03 orphaned listings, "Missing translations", "Invalid effective dates",
"Conflicting rules", "Safety constraints") are not typed exceptions here: `gate.py` reports them
as accumulated `GateError` records inside one `GateResult` instead of raising, since Sec 9
requires surfacing *every* simultaneous violation in one rejection, not just the first-raised
one.
"""

from __future__ import annotations


class DuplicateCodeError(ValueError):
    """Config Framework Sec 9 "Duplicate codes": a Code reused within an entity type."""

    def __init__(self, entity_type: str, code: str) -> None:
        self.entity_type = entity_type
        self.code = code
        super().__init__(f"code {code!r} already exists for entity type {entity_type!r}")


class DraftRequiredError(ValueError):
    """A mutation was attempted on a version that is not (or no longer) DRAFT -- published
    versions are immutable (Physical DB Sec 2.4, PD-07 guard trigger)."""

    def __init__(self, version_id: str, actual_status: str) -> None:
        self.version_id = version_id
        self.actual_status = actual_status
        super().__init__(f"version {version_id} is {actual_status}, not DRAFT")


class SelfApprovalError(ValueError):
    """Config Framework Sec 2.3: "the approver must be a different principal" -- the maker
    cannot also be the checker on a controlled-track publish."""

    def __init__(self) -> None:
        super().__init__("the approver must be a different principal from the author")


class ApproverPermissionError(ValueError):
    """The checker lacks the entity-specific approve permission key (Super-Admin-only for
    role-definition/platform-settings, Config Framework Sec 2.3)."""

    def __init__(self, entity_type: str) -> None:
        self.entity_type = entity_type
        super().__init__(f"caller lacks the approve permission for {entity_type!r}")
