"""UNF-012: grants an already-registered account the `super-admin` role. No API path can do this
for the FIRST administrator -- `POST /admin/users/{id}/roles` (`assignRole`, ADR-0006) itself
requires `identity:role:assign`, which nobody holds on a fresh install (a real chicken-and-egg:
the only way to grant that permission is already holding it). Every other operator task in this
situation (`docs/assessments/2026-07-27-verification/evidence/harness/bootstrap_admin.py`) has
had to fall back to a raw `INSERT INTO identity.role_assignment`, which this script replaces with
the real use case (`AdminIdentityUseCases.assign_role`) -- the same one `assignRole`'s own router
calls, so the assignment is indistinguishable from one a real super-admin granted.

Deliberately narrow: it does not create the account (register normally first, e.g. `POST
/auth/register/email`) and does not grant any role other than `super-admin` -- routine role
grants belong on `assignRole` once a first super-admin exists to call it.

Run: python -m bootstrap_admin <email> (from apps/backend/src, matching how `main.py`/
`search_worker.py` are invoked). Idempotent -- `UserAccount.assign_role`'s own domain method
supersedes a prior assignment for the same role rather than duplicating it, so re-running against
an account that already holds `super-admin` is a safe no-op change.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime

import composition_root
from identity.domain.user_account import UserAccount
from identity.domain.value_objects import EmailAddress
from identity.infrastructure.persistence.repository import SqlalchemyUserAccountRepository

_SUPER_ADMIN_ROLE_CODE = "super-admin"


async def _bootstrap(email: str) -> None:
    address = EmailAddress(value=email)
    found: list[UserAccount | None] = []

    # Deliberately no `break`/early return inside either loop: `session_scope`'s commit runs on
    # the generator's own clean exhaustion (both of these yield exactly once regardless), and an
    # early exit instead raises GeneratorExit through it -- harmless for the read-only lookup
    # below, but the write loop needs the commit to actually happen.
    async for session in composition_root._identity_session():
        found.append(await SqlalchemyUserAccountRepository(session).get_by_email(address))

    account = found[0]
    if account is None:
        sys.exit(
            f"no account registered with email {email!r} -- register it first "
            "(POST /auth/register/email), then re-run this script"
        )
    target_id = account.id

    async for use_cases in composition_root.provide_admin_identity_use_cases():
        await use_cases.assign_role(
            actor_id=target_id,
            target_account_id=target_id,
            role_code=_SUPER_ADMIN_ROLE_CODE,
            acting_profile_id=None,
            now=datetime.now(UTC),
        )

    print(f"{email} ({target_id.value}) -> {_SUPER_ADMIN_ROLE_CODE}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python -m bootstrap_admin <email>")
    asyncio.run(_bootstrap(sys.argv[1]))
