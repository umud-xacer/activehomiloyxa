"""billing -- DTOs (Task P-01). Translated field-for-field from the OpenAPI
operations tagged to this module (contracts/openapi.yaml). Schema only: no aggregate
type is exposed here, no business behaviour, no validation beyond what Pydantic
itself does structurally.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from active_home_shared import CamelModel
from shared_kernel import LocalizedText, Money


class PageInfo(CamelModel):
    """Cursor pagination metadata (OpenAPI `CursorPage.page`)."""

    limit: int
    next_cursor: str | None = None
    """Pass as `cursor` to fetch the next page; null when exhausted."""
    total: int | None = None
    """Present only where cheap to compute; may be null."""


class Invoice(CamelModel):
    """Offline billing document (one per order). Settled by operator confirmation (DEC-02)."""

    id: UUID
    order_id: UUID
    invoice_number: str
    amount: Money
    status: Literal["ISSUED", "PAID", "VOID"]
    issued_at: datetime
    payment_confirmed_at: datetime | None = None


class InvoicePage(CamelModel):
    """A cursor-paginated page of `Invoice` (OpenAPI `CursorPage` composed with
    `items: Invoice[]` via `allOf`)."""

    items: list[Invoice]
    page: PageInfo


class PaymentConfirmationRequest(CamelModel):
    """Operator records confirmation of an offline payment (FR-BILL-002). Activates entitlements."""

    confirmed: bool
    note: str | None = None


class OrderCreateRequest(CamelModel):
    """OpenAPI `OrderCreateRequest`."""

    product_id: UUID
    target_type: Literal["PROFILE", "LISTING", "SLOT_BOOKING"]
    target_id: UUID | None = None
    """Required for LISTING and SLOT_BOOKING targets."""


class Order(CamelModel):
    """A purchase request; freezes a ProductSnapshot (BC-08)."""

    id: UUID
    purchaser_profile_id: UUID
    product_id: UUID
    target_type: Literal["PROFILE", "LISTING", "SLOT_BOOKING"] | None = None
    target_id: UUID | None = None
    amount: Money
    status: Literal["PENDING", "INVOICED", "PAID", "FULFILLED", "CANCELLED"]
    invoice_id: UUID | None = None
    created_at: datetime


class Entitlement(CamelModel):
    """OpenAPI `Entitlement`."""

    id: UUID
    order_id: UUID | None = None
    entitlement_type: Literal[
        "ACTIVE_SUBSCRIPTION",
        "LISTING_PROMOTION",
        "VERIFICATION_ELIGIBILITY",
        "BANNER_SLOT_BOOKING",
        "LISTING_PUBLICATION",
        "LISTING_CREDIT_BALANCE",
    ]
    promotion_kind: Literal["PREMIUM", "FEATURED", "TOP_PLACEMENT"] | None = None
    target_id: UUID | None = None
    valid_from: datetime
    valid_until: datetime
    activation_state: Literal["ACTIVE", "EXPIRED", "REVOKED"]
    remaining_credits: int | None = None
    """`LISTING_CREDIT_BALANCE` only -- `None` means unlimited (the Unlim tier) for that
    entitlement type, but also just "not applicable" for every other type (2026-08-24, exposed
    for the admin credit-balance panel -- was tracked on the domain aggregate since Phase 4 but
    never surfaced over the wire until now)."""


class OrderPage(CamelModel):
    """A cursor-paginated page of `Order` (OpenAPI `CursorPage` composed with
    `items: Order[]` via `allOf`)."""

    items: list[Order]
    page: PageInfo


class Product(CamelModel):
    """A purchasable product/plan (eight closed types). Read projection of the configured
    ProductDefinition."""

    id: UUID
    code: str
    product_type: Literal[
        "SUBSCRIPTION",
        "PREMIUM",
        "FEATURED",
        "TOP_PLACEMENT",
        "VERIFICATION",
        "BANNER_PLACEMENT",
        "LISTING_PUBLICATION",
        "LISTING_CREDIT_PACK",
    ]
    name: LocalizedText
    description: LocalizedText | None = None
    price: Money
    term_days: int | None = None
    quota: dict[str, Any] | None = None
    """For SUBSCRIPTION — listing quotas/limits (BRULE-07)."""
    category_id: UUID | None = None
    """LISTING_PUBLICATION only — a category-specific price override; null is the
    platform-default price (2026-08-23, listing paywall)."""


class PricingPlans(CamelModel):
    """`getPricingPlans` response (2026-08-23, listing paywall): the single-listing publish
    price resolved for one category (or the platform default) plus every bulk credit-pack
    tier -- the exact shape the frontend Paywall Modal's 3 purchase options need."""

    single_listing: Product | None = None
    credit_packs: list[Product]


class GrantCreditsRequest(CamelModel):
    """`adminGrantListingCredits` request body (2026-08-24): the admin picks WHICH published
    product to grant (a real, priced product -- typically a zero-price "Admin sovg'a" one
    authored via the owner-admin pricing UI, but any published product works, e.g. comping a real
    paid pack). Deliberately reuses the real `createOrder`+`confirmInvoicePayment` path end to
    end (not a bypass) -- see `admin_grant_listing_credits`'s own docstring. Serves two admin
    actions with one endpoint: a `LISTING_CREDIT_PACK`/`LISTING_PUBLICATION` product with no
    `targetId` grants the profile itself credits (`/admin/users`'s panel); a `PREMIUM`/
    `FEATURED`/`TOP_PLACEMENT` product with `targetId` set to a real listing id grants that
    listing VIP/TOP promotion (`/admin/listings`'s panel) -- `targetType` must match whichever
    the chosen product actually is (`TargetRef`'s own domain invariant, re-checked by
    `Order.create`, not merely declared here)."""

    product_id: UUID
    target_type: Literal["PROFILE", "LISTING"] = "PROFILE"
    target_id: UUID | None = None
    """Required (a real listing id) when `target_type` is `LISTING`; must stay `None` for
    `PROFILE` (the profile granted is always `profileId` from the URL path)."""
    note: str | None = None


class PaymentProviderStatus(CamelModel):
    """`adminGetPaymentProviderStatus` response (2026-08-24): whether each gateway's SECRET is
    present server-side (`PAYME_SECRET_KEY`/`CLICK_SECRET_KEY`) -- never the secret's value
    itself, this is a status light for `/admin/settings`, not a credentials editor (deliberate:
    payment secrets live in `.env` only, never in the DB or a web-editable form -- see
    `composition_root.provide_payment_provider_status`'s own docstring for why)."""

    payme_configured: bool
    click_configured: bool
    mock_enabled: bool
    """`PAYMENT_PROVIDER=mock` -- the demo/Uzum-labeled instant-pay endpoint is reachable."""
    uzum_available: bool = False
    """Always `False` in v1 -- no real Uzum Pay adapter exists yet (no merchant API
    documentation was available to build one against). Kept as an explicit field (not just
    omitted) so the admin UI always shows all three providers, one openly marked "not built"
    rather than silently missing."""
