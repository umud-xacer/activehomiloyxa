"""The FastAPI dependency shapes resolved by `interfaces/di.py::get_acting_user`/
`get_acting_operator`. Mirrors `catalog.interfaces.auth.ActingUser`'s own docstring exactly -- the
concrete resolution logic (reading the `ah_session` cookie, hashing it, calling identity's real
`ApplicationAuthorizationService`/`AuthorizationService`) lives at the composition root, the one
place allowed to see both modules' internals; billing's own source never imports identity, the
same self-imposed discipline catalog already established (even though SAD Sec 8.1's static
dependency table technically permits `billing -> identity`, unlike `search -> identity`, which
`search-scope` forbids outright).

`ActingOperator` backs the one admin-facing operation this module owns
(`confirmInvoicePayment`) -- by the time this dependency resolves, the composition root has
already run the real Gate-3 permission check (`billing:invoice:confirm_payment`); the router only
ever needs the operator's own account id (`PaymentConfirmation.confirmed_by`, FR-BILL-002)."""

from __future__ import annotations

from dataclasses import dataclass

from shared_kernel import BusinessProfileId, UserId


@dataclass(frozen=True)
class ActingUser:
    """The purchaser-facing acting identity (`createOrder`/`listMyOrders`/`getOrder`/
    `getOrderInvoice`/`listMyEntitlements`). `acting_profile_id` carries `Session.acting_context`
    (`null` = personal context) -- unlike catalog's own `ActingUser`, billing's own use cases
    reject a `None` value at the point of use (`Order.purchaserProfileId` is a required OpenAPI
    field, never nullable: every v1 purchase is business-profile-scoped)."""

    account_id: UserId
    acting_profile_id: BusinessProfileId | None


@dataclass(frozen=True)
class ActingOperator:
    """The admin-facing acting identity (`confirmInvoicePayment`)."""

    account_id: UserId
