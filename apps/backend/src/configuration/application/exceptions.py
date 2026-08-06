"""Application-level exceptions -- orchestration failures that are not themselves domain
invariant violations (those live in `domain/exceptions.py`). Mapped to `contracts.errors.Problem`
responses by the interfaces-layer router (404/409/422)."""

from __future__ import annotations

from configuration.domain import GateResult


class ConfigHeadNotFoundError(LookupError):
    def __init__(self, entity_type: str, head_id: str) -> None:
        self.entity_type = entity_type
        self.head_id = head_id
        super().__init__(f"no {entity_type} head {head_id}")


class ConfigVersionNotFoundError(LookupError):
    def __init__(self, entity_type: str, head_id: str, version_id: str) -> None:
        self.entity_type = entity_type
        self.head_id = head_id
        self.version_id = version_id
        super().__init__(f"no {entity_type} version {version_id} on head {head_id}")


class VersionNotPublishableError(ValueError):
    """The version is already PUBLISHED/DEPRECATED/ARCHIVED -- publish is only legal from
    DRAFT/VALIDATION/APPROVAL."""

    def __init__(self, version_id: str, actual_status: str) -> None:
        self.version_id = version_id
        self.actual_status = actual_status
        super().__init__(
            f"version {version_id} is {actual_status}; publish is not legal from this status"
        )


class GateFailedError(ValueError):
    """The pre-activation gate rejected the content -- publish/rollback is refused (Config
    Framework Sec 9: "A change failing any check is refused with a precise reason; it stays in
    Draft/Validation and is never published")."""

    def __init__(self, result: GateResult) -> None:
        self.result = result
        super().__init__(f"validation gate failed with {len(result.errors)} error(s)")


class InvalidDraftRequestError(ValueError):
    """A `ConfigurationDraftRequest` is missing a field only conditionally required by the
    OpenAPI schema (e.g. `code`/`businessOwner` are required when creating a *new* head, but not
    when creating a subsequent draft version on an existing one) -- an interfaces-layer input
    shape failure, not a domain invariant violation."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
