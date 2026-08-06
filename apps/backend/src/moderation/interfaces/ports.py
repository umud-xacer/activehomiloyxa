"""moderation -- ports (Task P-01). Abstract surface only (typing.Protocol): no
implementation, no aggregates, no ORM types. Each method's docstring cites the
OpenAPI operationId it derives from, for traceability back to contracts/openapi.yaml.
"""

from __future__ import annotations

from typing import Literal, Protocol
from uuid import UUID

from moderation.interfaces.dto import (
    ModerationActionRequest,
    ModerationCase,
    ModerationCasePage,
)


class ModerationPort(Protocol):
    """Derived from OpenAPI operations: `applyModerationAction`, `getModerationCase`, `listModerationQueue`."""

    async def apply_moderation_action(
        self, case_id: UUID, body: ModerationActionRequest
    ) -> ModerationCase:
        """`POST /admin/moderation-queue/{caseId}/action` (operationId `applyModerationAction`). Resolve a moderation case"""
        ...

    async def get_moderation_case(self, case_id: UUID) -> ModerationCase:
        """`GET /admin/moderation-queue/{caseId}` (operationId `getModerationCase`). Get a moderation case"""
        ...

    async def list_moderation_queue(
        self,
        status: Literal["OPEN", "IN_REVIEW", "RESOLVED"] | None = None,
        subject_type: Literal["LISTING", "CONVERSATION", "USER", "PROFILE"] | None = None,
        cursor: str | None = None,
        limit: int | None = 20,
    ) -> ModerationCasePage:
        """`GET /admin/moderation-queue` (operationId `listModerationQueue`). List moderation cases"""
        ...


class ModerationCommandTargetPort(Protocol):
    """SAD Sec 7.2: moderation "issues runtime commands to targets via their interfaces" (e.g. hide
    a listing, suspend an account) -- this is moderation *calling* catalog's/identity's own
    interfaces/ ports at runtime, not a port moderation exposes itself, so there is nothing to
    stub here beyond this note (SAD Sec 8.1: moderation MAY statically import shared_kernel
    only; it reaches targets through their published interfaces, never a static dependency)."""
