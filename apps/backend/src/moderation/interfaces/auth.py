"""The FastAPI dependency shape resolved by `interfaces/di.py::get_acting_moderator` (Security
Sec 4.2 Gates 1-3). Mirrors `profiles.interfaces.auth.ActingReviewer`'s own docstring exactly --
every moderation-tagged operation this module owns is moderator-only (there is no self-service
surface here; report submission is messaging's own `createReport` operation, Task P-10)."""

from __future__ import annotations

from dataclasses import dataclass

from shared_kernel import UserId


@dataclass(frozen=True)
class ActingModerator:
    account_id: UserId
