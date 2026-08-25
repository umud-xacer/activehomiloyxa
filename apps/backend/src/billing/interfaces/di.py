"""Composition-root OVERRIDE POINTS for billing's router dependencies (mirrors
`catalog.interfaces.di`'s own docstring exactly: DIP -- `billing.interfaces` never imports
`billing.infrastructure`, `no-infra-inbound-billing` tools/importlinter.cfg). These functions
exist only so `billing/interfaces/routers.py` has a stable, importable `Depends(...)` target; the
real implementation is registered by the app factory via `app.dependency_overrides[...]`
(`apps/backend/src/composition_root.py`, imported only from `apps/backend/src/main.py`)."""

from __future__ import annotations

from dataclasses import dataclass

from billing.application import EntitlementUseCases, OrderUseCases, PaymentUseCases
from billing.interfaces.auth import ActingOperator, ActingUser
from billing.interfaces.dto import PaymentProviderStatus


async def get_order_use_cases() -> OrderUseCases:
    raise NotImplementedError(
        "get_order_use_cases was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


@dataclass(frozen=True)
class AdminGrantCreditsUseCases:
    """`orders`/`payments` MUST be built from the same DB session (unlike `get_order_use_cases`/
    `get_payment_use_cases`, which are always used from two separate HTTP requests in every other
    caller -- a buyer's `createOrder` commits, then a LATER `confirmInvoicePayment` request reads
    the now-committed invoice). `admin_grant_listing_credits` composes `create_order` +
    `confirm_payment` in ONE request, so a just-created, not-yet-committed invoice would be
    invisible to a second, independently-transacted session (this is exactly the bug that produced
    `InvoiceNotFoundError` before this dependency existed -- 2026-08-25)."""

    orders: OrderUseCases
    payments: PaymentUseCases


async def get_admin_grant_credits_use_cases() -> AdminGrantCreditsUseCases:
    raise NotImplementedError(
        "get_admin_grant_credits_use_cases was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


async def get_payment_use_cases() -> PaymentUseCases:
    raise NotImplementedError(
        "get_payment_use_cases was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


async def get_entitlement_use_cases() -> EntitlementUseCases:
    raise NotImplementedError(
        "get_entitlement_use_cases was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


async def get_acting_user() -> ActingUser:
    raise NotImplementedError(
        "get_acting_user was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


async def get_acting_operator() -> ActingOperator:
    raise NotImplementedError(
        "get_acting_operator was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


def get_payment_provider_status() -> PaymentProviderStatus:
    raise NotImplementedError(
        "get_payment_provider_status was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )
