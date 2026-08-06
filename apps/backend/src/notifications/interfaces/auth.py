"""The FastAPI dependency shape resolved by `interfaces/di.py::get_acting_user` (Security Sec
4.2 Gates 1-2). Mirrors `media.interfaces.auth.ActingUser`'s own docstring: every
notifications-tagged operation this module owns is self-service only (a user reading/managing
their OWN notifications) -- no acting-profile context, no permission-key gate, ownership is
scoped structurally by `recipient_user_id` in every query."""

from __future__ import annotations

from dataclasses import dataclass

from shared_kernel import UserId


@dataclass(frozen=True)
class ActingUser:
    account_id: UserId
