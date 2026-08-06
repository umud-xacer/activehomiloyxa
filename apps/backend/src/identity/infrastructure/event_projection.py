"""identity/infrastructure -- P-20 fix (confirmed integration defect, found by the E2E critical-
journey suite): `UserAccount.owned_profile_ids` was never appended to after
`profiles.createBusinessProfile` succeeded -- no consumer reacted to `profiles.
BusinessProfileCreated` for this purpose (the frozen event's own docstring names only
"Analytics" as a consumer, but adding a new reaction to an ALREADY-published event is not a
contract change -- no new event, no payload change -- exactly the same precedent this task
already used for billing's `LISTING_PROMOTION` entitlement reaching catalog, and profiles'
verification events reaching search). Without this, a freshly created business profile could
never legitimately become a session's acting profile (`switchActingProfile` always raised
`ProfileNotOwnedError`), which transitively blocked `billing.createOrder`/`getOrderInvoice`
(both require an acting profile) -- a real, user-facing defect, not merely a test gap.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backbone.idempotency import idempotent_consume
from identity.application.account_use_cases import AccountUseCases
from identity.infrastructure.persistence.models import ProcessedEventRow
from shared_kernel import BusinessProfileId, EventEnvelope, UserId

_HANDLER_NAME = "identity.handle_profiles_event"


async def handle_profiles_event(
    session: AsyncSession, envelope: EventEnvelope, use_cases: AccountUseCases
) -> None:
    if envelope.event_type != "BusinessProfileCreated":
        return
    async with idempotent_consume(
        session, ProcessedEventRow, event_id=envelope.event_id, handler=_HANDLER_NAME
    ) as is_fresh:
        if not is_fresh:
            return
        owner_user_id_raw = envelope.payload.get("ownerUserId")
        profile_id_raw = envelope.payload.get("businessProfileId")
        if owner_user_id_raw is None or profile_id_raw is None:
            return
        await use_cases.link_owned_profile(
            UserId(value=UUID(str(owner_user_id_raw))),
            profile_id=BusinessProfileId(value=UUID(str(profile_id_raw))),
            now=envelope.occurred_at,
        )
