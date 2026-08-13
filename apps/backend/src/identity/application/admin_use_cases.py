"""identity/application -- administrative account/role use cases: suspend/reactivate, list users,
assign/revoke a role (Config Framework Sec 7.2). Backs `ActingIdentityQueryPort`'s
`admin_change_user_status`/`admin_list_users` and the P-05 prompt's "suspend-account"/
"assign-role" use cases.

Not mounted on any router in this task: `adminListUsers`/`adminChangeUserStatus` are tagged
`Administration` in contracts/openapi.yaml, not `Authentication`/`Users`, and role assignment has
no OpenAPI operation at all -- both are out of this task's router scope (P-05 prompt: "Authentication
+ Users API routers implementing exactly the OpenAPI operations tagged for this module"). This
class exists so the underlying capability is built and callable in-process today (via
`identity.interfaces`) rather than deferred wholesale -- a future `admin`-module task mounts the
HTTP surface over it without touching this file (AIR-01).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from contracts.events.identity import (
    AccountClosed,
    AccountSuspended,
    RegistrationApproved,
    RegistrationRejected,
)
from identity.application.exceptions import AccountNotFoundError
from identity.application.ports import (
    RoleDefinitionReaderPort,
    SessionRepository,
    UserAccountRepository,
)
from identity.domain import RegistrationReviewStatus, UserAccount
from shared_kernel import BusinessProfileId, OutboxPort, UserId


class AdminIdentityUseCases:
    def __init__(
        self,
        *,
        accounts: UserAccountRepository,
        sessions: SessionRepository,
        outbox: OutboxPort,
        role_reader: RoleDefinitionReaderPort,
    ) -> None:
        self._accounts = accounts
        self._sessions = sessions
        self._outbox = outbox
        self._role_reader = role_reader

    async def change_user_status(
        self,
        *,
        target_account_id: UserId,
        action: Literal["SUSPEND", "REACTIVATE", "CLOSE"],
        reason: str | None,
        now: datetime,
    ) -> UserAccount:
        """adminChangeUserStatus. Suspension triggers bulk session revocation (Security Sec 3.3)
        and publishes `AccountSuspended` (DDD Sec 6: "Operator suspension"). `CLOSE` is the
        owner-admin panel's "permanently remove user" action -- same anonymise-and-retain
        transition `UserAccount.close`/`AccountUseCases.close_account` already give a user over
        their own account (FR-USER-005), just admin-triggered instead of self-service; terminal,
        no reactivate path back out of CLOSED."""
        account = await self._require_account(target_account_id)
        if action == "SUSPEND":
            updated = account.suspend(now=now)
            await self._accounts.save(updated)
            await self._sessions.delete_all_for_account(target_account_id)
            event = AccountSuspended(
                event_id=uuid4(),
                occurred_at=now,
                actor=target_account_id.value,
                aggregate_type="UserAccount",
                aggregate_id=target_account_id.value,
                payload={"accountId": str(target_account_id.value), "reason": reason},
            )
            await self._outbox.append(event)
        elif action == "CLOSE":
            updated = account.close(now=now)
            await self._accounts.save(updated)
            await self._sessions.delete_all_for_account(target_account_id)
            event = AccountClosed(
                event_id=uuid4(),
                occurred_at=now,
                actor=target_account_id.value,
                aggregate_type="UserAccount",
                aggregate_id=target_account_id.value,
                payload={"accountId": str(target_account_id.value), "reason": reason},
            )
            await self._outbox.append(event)
        else:
            updated = account.reactivate(now=now)
            await self._accounts.save(updated)
        return updated

    async def list_users(
        self,
        *,
        status: str | None,
        query: str | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[UserAccount], str | None]:
        return await self._accounts.list_page(
            status=status, query=query, cursor=cursor, limit=limit
        )

    async def count_users(self) -> int:
        return await self._accounts.count_all()

    async def assign_role(
        self,
        *,
        actor_id: UserId,
        target_account_id: UserId,
        role_code: str,
        acting_profile_id: BusinessProfileId | None,
        now: datetime,
    ) -> UserAccount:
        """Config Framework Sec 7.2: pins the identity + the exact published RoleDefinition
        version at assignment time."""
        account = await self._require_account(target_account_id)
        resolved = await self._role_reader.resolve_by_code(role_code)
        updated = account.assign_role(
            role_definition_head_id=resolved.head_id,
            role_definition_version_id=resolved.version_id,
            role_code=resolved.code,
            acting_profile_id=acting_profile_id,
            assigned_by=actor_id.value,
            now=now,
        )
        await self._accounts.save(updated)
        return updated

    async def revoke_role(
        self,
        *,
        target_account_id: UserId,
        role_definition_head_id: UUID,
        acting_profile_id: BusinessProfileId | None,
        now: datetime,
    ) -> UserAccount:
        account = await self._require_account(target_account_id)
        updated = account.revoke_role(
            role_definition_head_id=role_definition_head_id,
            acting_profile_id=acting_profile_id,
            now=now,
        )
        await self._accounts.save(updated)
        return updated

    # --- registration review (ADR-0007) -----------------------------------------------------

    async def list_registration_queue(
        self, *, cursor: str | None, limit: int
    ) -> tuple[list[UserAccount], str | None]:
        """listRegistrationQueue. Reviewer-only (`identity:registration:review`, checked at the
        router/composition-root layer -- see `interfaces/di.py::get_acting_registration_
        reviewer`), mirrors `profiles.VerificationUseCases.list_queue`'s shape."""
        return await self._accounts.list_pending_review(cursor=cursor, limit=limit)

    async def decide_registration(
        self,
        *,
        target_account_id: UserId,
        reviewer_user_id: UserId,
        outcome: RegistrationReviewStatus,
        reason: str | None,
        now: datetime,
    ) -> UserAccount:
        """decideRegistration. `outcome` must be `APPROVED` or `REJECTED` (the router only ever
        passes one of the two, translated from `RegistrationDecisionRequest.outcome`) -- mirrors
        `profiles.VerificationUseCases.decide_verification`'s shape."""
        account = await self._require_account(target_account_id)
        decided = account.decide_registration(
            outcome=outcome, reason=reason, reviewer_user_id=reviewer_user_id.value, now=now
        )
        await self._accounts.save(decided)

        event_cls = (
            RegistrationApproved
            if outcome is RegistrationReviewStatus.APPROVED
            else RegistrationRejected
        )
        await self._outbox.append(
            event_cls(
                event_id=uuid4(),
                occurred_at=now,
                actor=reviewer_user_id.value,
                aggregate_type="UserAccount",
                aggregate_id=target_account_id.value,
                payload={"accountId": str(target_account_id.value), "reason": reason},
            )
        )
        return decided

    async def _require_account(self, account_id: UserId) -> UserAccount:
        account = await self._accounts.get_by_id(account_id)
        if account is None:
            raise AccountNotFoundError(account_id.value)
        return account
