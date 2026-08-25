"""FastAPI routers implementing exactly the eight billing-related OpenAPI operations
(`contracts/openapi.yaml`): six tagged `Billing` (`listProducts`, `listMyOrders`, `createOrder`,
`getOrder`, `getOrderInvoice`, `listMyEntitlements`) and two tagged `Administration`
(`adminListInvoices`, `confirmInvoicePayment`) -- both admin operations act purely on billing's
own aggregates (`Invoice`/`Order`/`Entitlement`), so they are implemented here, mirroring
`configuration.interfaces.routers`'s own precedent exactly (`admin_config_router` lives inside
`configuration/interfaces/`, not deferred to a future `admin` module -- the OpenAPI tag is a
documentation grouping, not a module-ownership signal). Thin translation only: path/body -> use
case call -> domain object -> already-frozen `interfaces/dto.py` DTO. All business logic lives in
`application`/`domain`; this module owns none.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from billing.application import (
    EntitlementUseCases,
    InvoiceNotFoundError,
    NoActingProfileError,
    OrderUseCases,
    PaymentUseCases,
)
from billing.application.ports import ProductDefinitionSnapshot
from billing.domain import Entitlement, Invoice, Order, ProductType, TargetType
from billing.interfaces.auth import ActingOperator, ActingUser
from billing.interfaces.di import (
    AdminGrantCreditsUseCases,
    get_acting_operator,
    get_acting_user,
    get_admin_grant_credits_use_cases,
    get_entitlement_use_cases,
    get_order_use_cases,
    get_payment_provider_status,
    get_payment_use_cases,
)
from billing.interfaces.dto import (
    Entitlement as EntitlementDto,
)
from billing.interfaces.dto import (
    GrantCreditsRequest,
    InvoicePage,
    OrderCreateRequest,
    OrderPage,
    PageInfo,
    PaymentConfirmationRequest,
    PaymentProviderStatus,
    PricingPlans,
    Product,
)
from billing.interfaces.dto import (
    Invoice as InvoiceDto,
)
from billing.interfaces.dto import (
    Order as OrderDto,
)
from shared_kernel import BusinessProfileId, Money

billing_router = APIRouter(tags=["Billing"])
admin_billing_router = APIRouter(tags=["Administration"])


def _acting_profile(user: ActingUser) -> BusinessProfileId:
    if user.acting_profile_id is None:
        raise NoActingProfileError()
    return user.acting_profile_id


def _clamp_limit(limit: int | None) -> int:
    return min(max(limit or 20, 1), 100)


def _to_product_dto(product: ProductDefinitionSnapshot) -> Product:
    return Product(
        id=product.id,
        code=product.code,
        product_type=product.product_type.value,
        name=product.name,
        description=product.description,
        price=Money(amount=Decimal(product.price_amount), currency=product.price_currency),
        term_days=product.term_days,
        quota=product.quota,
        category_id=product.category_id,
    )


def _to_order_dto(order: Order, *, invoice_id: UUID | None) -> OrderDto:
    return OrderDto(
        id=order.id,
        purchaser_profile_id=order.purchaser_profile_id.value,
        product_id=order.product_snapshot.product_definition_id,
        target_type=order.target.target_type.value,
        target_id=order.target.target_id,
        amount=order.amount,
        status=order.status.value,
        invoice_id=invoice_id,
        created_at=order.created_at,
    )


def _to_invoice_dto(invoice: Invoice) -> InvoiceDto:
    return InvoiceDto(
        id=invoice.id,
        order_id=invoice.order_id,
        invoice_number=invoice.invoice_number,
        amount=invoice.amount,
        status=invoice.status.value,
        issued_at=invoice.issued_at,
        payment_confirmed_at=(
            invoice.payment_confirmation.confirmed_at if invoice.payment_confirmation else None
        ),
    )


def _to_entitlement_dto(entitlement: Entitlement) -> EntitlementDto:
    return EntitlementDto(
        id=entitlement.id,
        order_id=entitlement.order_id,
        entitlement_type=entitlement.entitlement_type.value,
        promotion_kind=entitlement.promotion_kind.value if entitlement.promotion_kind else None,
        target_id=entitlement.target_id,
        valid_from=entitlement.valid_from,
        valid_until=entitlement.valid_until,
        activation_state=entitlement.activation_state.value,
        remaining_credits=entitlement.remaining_credits,
    )


@billing_router.get("/products", operation_id="listProducts")
async def list_products(
    productType: Literal[
        "SUBSCRIPTION",
        "PREMIUM",
        "FEATURED",
        "TOP_PLACEMENT",
        "VERIFICATION",
        "BANNER_PLACEMENT",
        "LISTING_PUBLICATION",
        "LISTING_CREDIT_PACK",
    ]
    | None = None,
    use_cases: OrderUseCases = Depends(get_order_use_cases),
) -> list[Product]:
    products = await use_cases.list_products(
        product_type=ProductType(productType) if productType else None
    )
    return [_to_product_dto(product) for product in products]


@billing_router.get("/pricing-plans", operation_id="getPricingPlans")
async def get_pricing_plans(
    categoryId: UUID | None = None,
    use_cases: OrderUseCases = Depends(get_order_use_cases),
) -> PricingPlans:
    """Unauthenticated read of the listing-paywall price matrix (2026-08-23): the single-listing
    publish price (`categoryId`-specific override if one is seeded, else the platform default)
    plus every `LISTING_CREDIT_PACK` bulk tier. A thin reshape of `list_products` -- no new
    persistence, same config-driven source `listProducts` already reads."""
    publication_products = await use_cases.list_products(
        product_type=ProductType.LISTING_PUBLICATION
    )
    single_listing = None
    if categoryId is not None:
        single_listing = next(
            (p for p in publication_products if p.category_id == categoryId), None
        )
    if single_listing is None:
        single_listing = next((p for p in publication_products if p.category_id is None), None)

    credit_packs = await use_cases.list_products(product_type=ProductType.LISTING_CREDIT_PACK)

    return PricingPlans(
        single_listing=_to_product_dto(single_listing) if single_listing else None,
        credit_packs=[_to_product_dto(p) for p in credit_packs],
    )


@billing_router.get("/orders", operation_id="listMyOrders")
async def list_my_orders(
    cursor: str | None = None,
    limit: int | None = Query(default=20),
    user: ActingUser = Depends(get_acting_user),
    use_cases: OrderUseCases = Depends(get_order_use_cases),
) -> OrderPage:
    profile_id = _acting_profile(user)
    page_limit = _clamp_limit(limit)
    orders, next_cursor = await use_cases.list_my_orders(
        purchaser_profile_id=profile_id, cursor=cursor, limit=page_limit
    )
    items = []
    for order in orders:
        invoice = await use_cases.get_order_invoice(order.id)
        items.append(_to_order_dto(order, invoice_id=invoice.id if invoice else None))
    return OrderPage(items=items, page=PageInfo(limit=page_limit, next_cursor=next_cursor))


@billing_router.post("/orders", operation_id="createOrder", status_code=201)
async def create_order(
    body: OrderCreateRequest,
    user: ActingUser = Depends(get_acting_user),
    use_cases: OrderUseCases = Depends(get_order_use_cases),
) -> OrderDto:
    profile_id = _acting_profile(user)
    order = await use_cases.create_order(
        purchaser_profile_id=profile_id,
        product_id=body.product_id,
        target_type=TargetType(body.target_type),
        target_id=body.target_id,
        booking_window=None,
        now=datetime.now(UTC),
    )
    invoice = await use_cases.get_order_invoice(order.id)
    return _to_order_dto(order, invoice_id=invoice.id if invoice else None)


@billing_router.get("/orders/{orderId}", operation_id="getOrder")
async def get_order(
    orderId: UUID,
    user: ActingUser = Depends(get_acting_user),
    use_cases: OrderUseCases = Depends(get_order_use_cases),
) -> OrderDto:
    profile_id = _acting_profile(user)
    order = await use_cases.get_order(orderId, purchaser_profile_id=profile_id)
    invoice = await use_cases.get_order_invoice(order.id)
    return _to_order_dto(order, invoice_id=invoice.id if invoice else None)


@billing_router.get("/orders/{orderId}/invoice", operation_id="getOrderInvoice")
async def get_order_invoice(
    orderId: UUID,
    user: ActingUser = Depends(get_acting_user),
    use_cases: OrderUseCases = Depends(get_order_use_cases),
) -> InvoiceDto:
    profile_id = _acting_profile(user)
    order = await use_cases.get_order(orderId, purchaser_profile_id=profile_id)
    invoice = await use_cases.get_order_invoice(order.id)
    if invoice is None:
        raise InvoiceNotFoundError(order_id=order.id)
    return _to_invoice_dto(invoice)


@billing_router.get("/me/entitlements", operation_id="listMyEntitlements")
async def list_my_entitlements(
    activeOnly: bool = True,
    user: ActingUser = Depends(get_acting_user),
    use_cases: EntitlementUseCases = Depends(get_entitlement_use_cases),
) -> list[EntitlementDto]:
    profile_id = _acting_profile(user)
    entitlements = await use_cases.list_my_entitlements(
        purchaser_profile_id=profile_id, active_only=activeOnly
    )
    return [_to_entitlement_dto(e) for e in entitlements]


@admin_billing_router.get("/admin/billing/invoices", operation_id="adminListInvoices")
async def admin_list_invoices(
    status: Literal["ISSUED", "PAID", "VOID"] | None = None,
    cursor: str | None = None,
    limit: int | None = Query(default=20),
    _operator: ActingOperator = Depends(get_acting_operator),
    use_cases: PaymentUseCases = Depends(get_payment_use_cases),
) -> InvoicePage:
    page_limit = _clamp_limit(limit)
    invoices, next_cursor = await use_cases.admin_list_invoices(
        status=status, cursor=cursor, limit=page_limit
    )
    return InvoicePage(
        items=[_to_invoice_dto(invoice) for invoice in invoices],
        page=PageInfo(limit=page_limit, next_cursor=next_cursor),
    )


@admin_billing_router.post(
    "/admin/billing/invoices/{invoiceId}/confirm-payment",
    operation_id="confirmInvoicePayment",
)
async def confirm_invoice_payment(
    invoiceId: UUID,
    body: PaymentConfirmationRequest,
    operator: ActingOperator = Depends(get_acting_operator),
    use_cases: PaymentUseCases = Depends(get_payment_use_cases),
) -> InvoiceDto:
    invoice = await use_cases.confirm_payment(
        invoice_id=invoiceId,
        operator_account_id=operator.account_id.value,
        confirmed=body.confirmed,
        note=body.note,
        now=datetime.now(UTC),
    )
    return _to_invoice_dto(invoice)


@admin_billing_router.get(
    "/admin/billing/profiles/{profileId}/entitlements",
    operation_id="adminListProfileEntitlements",
)
async def admin_list_profile_entitlements(
    profileId: UUID,
    activeOnly: bool = True,
    _operator: ActingOperator = Depends(get_acting_operator),
    use_cases: EntitlementUseCases = Depends(get_entitlement_use_cases),
) -> list[EntitlementDto]:
    """`/admin/users`'s credit-balance panel (2026-08-24) -- `list_my_entitlements` was already
    profile-scoped by parameter, not by the caller's own session; this is the same use case call
    `listMyEntitlements` makes, just admin-gated and reading an ADMIN-CHOSEN profile id instead
    of the caller's own acting profile."""
    entitlements = await use_cases.list_my_entitlements(
        purchaser_profile_id=BusinessProfileId(value=profileId), active_only=activeOnly
    )
    return [_to_entitlement_dto(e) for e in entitlements]


@admin_billing_router.post(
    "/admin/billing/profiles/{profileId}/grant-credits",
    operation_id="adminGrantListingCredits",
)
async def admin_grant_listing_credits(
    profileId: UUID,
    body: GrantCreditsRequest,
    operator: ActingOperator = Depends(get_acting_operator),
    use_cases: AdminGrantCreditsUseCases = Depends(get_admin_grant_credits_use_cases),
) -> InvoiceDto:
    """Grants `body.productId`'s entitlement to `profileId` for free, admin-triggered (2026-08-24,
    `/admin/users`'s "Kredit qo'shish" action) -- NOT a bypass of billing's own invariants: every
    `Entitlement` still requires a real `order_id` (`Entitlement.order_id: UUID`, non-nullable),
    so this composes the exact same two real use-case calls a real Payme/Click/mock payment
    already makes (`OrderUseCases.create_order` then `PaymentUseCases.confirm_payment`), just
    admin-triggered instead of buyer-triggered against a real, published product (typically a
    zero-price "Admin sovg'a" product authored via the owner-admin pricing UI, but any published
    product works -- e.g. comping a normally-paid pack). A real `Order`/`Invoice` audit trail is
    the deliberate result, not an accident: `confirm_payment`'s own `note` records who granted it
    and why.

    `use_cases.orders`/`use_cases.payments` share ONE DB session (`AdminGrantCreditsUseCases`,
    `billing/interfaces/di.py`) -- unlike every other `create_order`/`confirm_payment` pairing,
    which always spans two separate HTTP requests (a buyer's `createOrder` commits before a LATER
    `confirmInvoicePayment` request reads it), this endpoint calls both in the same request, so a
    just-created, not-yet-committed invoice would be invisible to an independently-transacted
    `confirm_payment` (this produced a real `InvoiceNotFoundError` 404 in production, 2026-08-25,
    before `AdminGrantCreditsUseCases` existed -- do not revert to two separate `Depends(...)`)."""
    now = datetime.now(UTC)
    order = await use_cases.orders.create_order(
        purchaser_profile_id=BusinessProfileId(value=profileId),
        product_id=body.product_id,
        target_type=TargetType(body.target_type),
        target_id=body.target_id,
        booking_window=None,
        now=now,
    )
    invoice = await use_cases.orders.get_order_invoice(order.id)
    if invoice is None:
        raise InvoiceNotFoundError(order_id=order.id)
    confirmed = await use_cases.payments.confirm_payment(
        invoice_id=invoice.id,
        operator_account_id=operator.account_id.value,
        confirmed=True,
        note=body.note or "Admin panel orqali bepul berildi",
        now=now,
    )
    return _to_invoice_dto(confirmed)


@admin_billing_router.get(
    "/admin/billing/payment-providers/status",
    operation_id="adminGetPaymentProviderStatus",
)
async def admin_get_payment_provider_status(
    _operator: ActingOperator = Depends(get_acting_operator),
    status: PaymentProviderStatus = Depends(get_payment_provider_status),
) -> PaymentProviderStatus:
    """Read-only status light for `/admin/settings` (2026-08-24): whether Payme/Click's secrets
    are present server-side, never the secrets themselves -- see `PaymentProviderStatus`'s own
    docstring for why this stays read-only rather than becoming a credentials editor."""
    return status
