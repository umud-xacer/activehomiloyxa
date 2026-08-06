"""Registers messaging's typed domain/application exceptions onto the shared
`backbone.errors.ExceptionMapper` (the same registry `identity.interfaces.errors`/`billing.
interfaces.errors`/`search.interfaces.errors` extend). Called once from the composition root
(`apps/backend/src/main.py`) for the stateless HTTP tier's own app; the realtime runner has no
REST error surface of its own (a WebSocket close code communicates the same failures instead, see
`interfaces/ws.py`).

`RateLimitExceededError` maps to `429 RATE_LIMITED`, mirroring `identity.interfaces.errors`'s own
`OtpThrottledError` -> `429 OTP_THROTTLED` mapping exactly -- like that mapping, this does not
attach a `Retry-After`/`X-RateLimit-*` header (`simple_problem_builder` has no header-attachment
mechanism at all; no module has ever built one, a pre-existing, shared gap against Security Sec
3.1's own requirement, not unique to or newly introduced by this task)."""

from __future__ import annotations

from backbone.errors import ExceptionMapper, simple_problem_builder
from messaging.application.exceptions import (
    BlockAlreadyExistsError,
    ConversationAlreadyExistsError,
    ConversationNotFoundError,
    ListingOwnerUnknownError,
)
from messaging.domain import (
    BlockedParticipantError,
    EmptyMessageBodyError,
    IllegalConversationStateTransitionError,
    NotAParticipantError,
    RateLimitExceededError,
    SelfBlockError,
    SelfConversationError,
)


def register_messaging_exception_mappings(mapper: ExceptionMapper) -> None:
    # --- validation (422) -----------------------------------------------------------------------
    mapper.register(
        EmptyMessageBodyError,
        simple_problem_builder(
            status=422, code="VALIDATION_FAILED", title="Message body must not be empty"
        ),
    )
    mapper.register(
        SelfConversationError,
        simple_problem_builder(
            status=422, code="VALIDATION_FAILED", title="Cannot start a conversation with yourself"
        ),
    )
    mapper.register(
        SelfBlockError,
        simple_problem_builder(status=422, code="VALIDATION_FAILED", title="Cannot block yourself"),
    )

    # --- not found (404) -------------------------------------------------------------------------
    mapper.register(
        ConversationNotFoundError,
        simple_problem_builder(
            status=404, code="RESOURCE_NOT_FOUND", title="Conversation not found"
        ),
    )

    # --- authorization (403) --------------------------------------------------------------------
    mapper.register(
        NotAParticipantError,
        simple_problem_builder(
            status=403,
            code="PERMISSION_DENIED",
            title="Caller is not a participant of this conversation",
        ),
    )
    mapper.register(
        BlockedParticipantError,
        simple_problem_builder(
            status=403, code="PERMISSION_DENIED", title="The recipient has blocked the sender"
        ),
    )

    # --- conflict (409) -------------------------------------------------------------------------
    mapper.register(
        ConversationAlreadyExistsError,
        simple_problem_builder(
            status=409,
            code="DUPLICATE_KEY",
            title="A conversation already exists for this listing and initiator",
        ),
    )
    mapper.register(
        BlockAlreadyExistsError,
        simple_problem_builder(status=409, code="DUPLICATE_KEY", title="User is already blocked"),
    )
    mapper.register(
        IllegalConversationStateTransitionError,
        simple_problem_builder(
            status=409,
            code="ILLEGAL_STATE_TRANSITION",
            title="Conversation cannot make that transition",
        ),
    )

    # --- rate limiting (429) ---------------------------------------------------------------------
    mapper.register(
        RateLimitExceededError,
        simple_problem_builder(
            status=429, code="RATE_LIMITED", title="Messaging rate limit exceeded"
        ),
    )

    # --- dependency degraded (503) ----------------------------------------------------------------
    mapper.register(
        ListingOwnerUnknownError,
        simple_problem_builder(
            status=503,
            code="DEPENDENCY_DEGRADED",
            title="This listing's owner has not yet been observed",
        ),
    )
