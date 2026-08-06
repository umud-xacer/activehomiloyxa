"""moderation/application -- `ModerationActionService [P]` (DDD Sec 5.11: "executes the verb by
issuing commands to BC-03 (listing state) or BC-01 (account suspension) through their explicit
interfaces" -- extended by ADR-0003 with BC-02/profiles as a third target). This is the module's
single most important class: the ONLY place a resolved `ModerationCase`'s `ResolutionAction`
turns into an actual cross-module command, and it does so ONLY through the three narrow
`application.ports` Protocols -- never a static import, never a direct write to another module's
tables, never a reimplementation of another module's state machine (the "interface-only-action"
guarantee `test_interface_only_action.py` proves by import-linter + integration inspection).
"""

from __future__ import annotations

from moderation.application.exceptions import UnresolvedModerationCaseError
from moderation.application.ports import (
    AccountSuspensionCommandPort,
    ListingModerationCommandPort,
    ProfileModerationCommandPort,
)
from moderation.domain import ModerationCase, ResolutionAction

_NO_TARGET_COMMAND_ACTIONS = frozenset(
    {ResolutionAction.REQUEST_CORRECTION, ResolutionAction.DISMISS}
)
"""Neither verb changes another module's own state: `RequestCorrection` is a recorded request to
the content owner (no visibility change -- BRULE-17's post-publication content stays live while
the owner is asked to fix it); `Dismiss` closes the case with no action taken. Both are fully
satisfied by `ModerationCase.resolve`'s own decision record -- no command port call at all."""


class ModerationActionService:
    def __init__(
        self,
        *,
        listings: ListingModerationCommandPort,
        accounts: AccountSuspensionCommandPort,
        profiles: ProfileModerationCommandPort,
    ) -> None:
        self._listings = listings
        self._accounts = accounts
        self._profiles = profiles

    async def execute(self, case: ModerationCase) -> None:
        """Requires `case.resolution` to already be set (i.e. `case.resolve(...)` has already run
        and produced the `ModerationCase` passed in) -- this method only dispatches the already-
        decided verb to its target, it does not itself decide anything (that is the aggregate's
        own job, `ModerationCase.resolve`, which already validated the action is legal for this
        subject type via `InvalidResolutionForSubjectError`)."""
        if case.resolution is None:
            raise UnresolvedModerationCaseError(case.id)
        action = case.resolution.action
        subject_id = case.subject.subject_id
        moderator_user_id = case.resolution.moderator_user_id
        reason = case.resolution.note

        if action is ResolutionAction.HIDE:
            await self._listings.hide_listing(
                subject_id, moderator_user_id=moderator_user_id, reason=reason
            )
        elif action is ResolutionAction.REJECT:
            await self._listings.reject_listing(
                subject_id, moderator_user_id=moderator_user_id, reason=reason
            )
        elif action is ResolutionAction.SUSPEND:
            await self._listings.suspend_listing(
                subject_id, moderator_user_id=moderator_user_id, reason=reason
            )
        elif action is ResolutionAction.REMOVE:
            await self._listings.remove_listing(
                subject_id, moderator_user_id=moderator_user_id, reason=reason
            )
        elif action is ResolutionAction.SUSPEND_ACCOUNT:
            await self._accounts.suspend_account(subject_id, reason=reason)
        elif action is ResolutionAction.REVOKE_BADGE:
            await self._profiles.revoke_badge(subject_id)
        elif action is ResolutionAction.ARCHIVE_PROFILE:
            await self._profiles.archive_profile(subject_id)
        elif action in _NO_TARGET_COMMAND_ACTIONS:
            return
        else:  # pragma: no cover -- unreachable: ResolutionAction is a closed enum, every member handled above
            raise AssertionError(f"unhandled ResolutionAction: {action!r}")
