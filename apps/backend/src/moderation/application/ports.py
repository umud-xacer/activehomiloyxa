"""moderation/application -- ports (Task P-12). Abstract surface only (typing.Protocol);
`infrastructure/` implements every one of these, never the reverse (Clean Architecture rule 4).

The three command-target ports below (`ListingModerationCommandPort`/
`AccountSuspensionCommandPort`/`ProfileModerationCommandPort`) are moderation's OWN narrow local
Protocols -- NOT `catalog.interfaces.moderation_port.ListingModerationPort`/`identity.interfaces.
ports.ActingIdentityQueryPort`/`profiles.interfaces.moderation_port.ProfileModerationPort`
imported directly. SAD Sec 8.1's own moderation row is stricter than every other module's:
"shared_kernel (issues runtime commands via targets' interfaces)" -- moderation may NOT statically
import catalog/identity/profiles even in `infrastructure/` (`cross-module-moderation`,
tools/importlinter.cfg, forbids all three, unlike e.g. catalog's own `infrastructure/media_
adapter.py`, which may still import media). The CONCRETE bridge adapters implementing these
Protocols against the real target ports are therefore defined entirely in `composition_root.py`
(the one place allowed to see every module's internals), never inside `moderation/` itself --
mirrors `catalog.infrastructure.media_adapter._MediaReader`'s own narrow-Protocol-plus-
composition-root-bridge pattern, just with the bridge pushed one level further out (composition
root instead of `moderation/infrastructure/`) because moderation cannot import even the *narrow*
target module at all.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from moderation.domain import CaseStatus, ModerationCase, SubjectType


class ModerationCaseRepository(Protocol):
    async def get_by_id(self, case_id: UUID) -> ModerationCase | None: ...

    async def get_open_or_in_review_for_subject(
        self, subject_type: SubjectType, subject_id: UUID
    ) -> ModerationCase | None:
        """Backs "a report opens or attaches to a ModerationCase" (P-12 scope): a second report
        against a subject that already has a non-terminal case attaches to it rather than opening
        a duplicate. Returns `None` if no open/in-review case exists for this subject (a fresh
        case is then opened)."""
        ...

    async def add(self, case: ModerationCase) -> None: ...

    async def save(self, case: ModerationCase) -> ModerationCase: ...

    async def list_queue(
        self,
        *,
        status: CaseStatus | None,
        subject_type: SubjectType | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[ModerationCase], str | None]: ...


class ListingModerationCommandPort(Protocol):
    """Moderation's own narrow copy of `catalog.interfaces.moderation_port.
    ListingModerationPort`'s shape (Task P-12 additions) -- see module docstring for why this is
    a separate Protocol rather than importing catalog's own."""

    async def hide_listing(
        self, listing_id: UUID, *, moderator_user_id: UUID, reason: str | None
    ) -> None: ...

    async def reject_listing(
        self, listing_id: UUID, *, moderator_user_id: UUID, reason: str | None
    ) -> None: ...

    async def suspend_listing(
        self, listing_id: UUID, *, moderator_user_id: UUID, reason: str | None
    ) -> None: ...

    async def remove_listing(
        self, listing_id: UUID, *, moderator_user_id: UUID, reason: str | None
    ) -> None: ...

    async def unflag_listing(self, listing_id: UUID, *, reason: str | None) -> None: ...


class AccountSuspensionCommandPort(Protocol):
    """Moderation's own narrow copy of the one method it needs from identity's
    `ActingIdentityQueryPort.admin_change_user_status` (`identity/interfaces/ports.py`) -- FR-MOD-
    004: "allow an authorised operator to suspend or ban an account.\""""

    async def suspend_account(self, account_id: UUID, *, reason: str | None) -> None: ...


class ProfileModerationCommandPort(Protocol):
    """Moderation's own narrow copy of `profiles.interfaces.moderation_port.
    ProfileModerationPort`'s shape (ADR-0003)."""

    async def revoke_badge(self, profile_id: UUID) -> None: ...

    async def archive_profile(self, profile_id: UUID) -> None: ...
