"""moderation/application -- exceptions for facts the domain layer cannot know (missing rows).
Mirrors `profiles.application.exceptions`'s style: one base, typed subclasses named for the
condition they signal.
"""

from __future__ import annotations

from uuid import UUID


class ModerationApplicationError(Exception):
    """Base for every typed exception raised by moderation's application/ layer."""


class ModerationCaseNotFoundError(ModerationApplicationError):
    def __init__(self, case_id: UUID) -> None:
        self.case_id = case_id
        super().__init__(f"moderation case {case_id} not found")


class UnresolvedModerationCaseError(ModerationApplicationError):
    """Raised by `ModerationActionService.execute()` when passed a `ModerationCase` whose
    `resolution` is still unset -- `execute()` only dispatches an already-decided verb, it does
    not itself decide anything, so a case reaching it without a resolution is a caller-side
    precondition violation, not a domain-state fact."""

    def __init__(self, case_id: UUID) -> None:
        self.case_id = case_id
        super().__init__(f"moderation case {case_id} has no resolution to execute")
