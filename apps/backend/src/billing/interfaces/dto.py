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
    ]
    promotion_kind: Literal["PREMIUM", "FEATURED", "TOP_PLACEMENT"] | None = None
    target_id: UUID | None = None
    valid_from: datetime
    valid_until: datetime
    activation_state: Literal["ACTIVE", "EXPIRED", "REVOKED"]


class OrderPage(CamelModel):
    """A cursor-paginated page of `Order` (OpenAPI `CursorPage` composed with
    `items: Order[]` via `allOf`)."""

    items: list[Order]
    page: PageInfo


class Product(CamelModel):
    """A purchasable product/plan (six closed types). Read projection of the configured
    ProductDefinition."""

    id: UUID
    code: str
    product_type: Literal[
        "SUBSCRIPTION", "PREMIUM", "FEATURED", "TOP_PLACEMENT", "VERIFICATION", "BANNER_PLACEMENT"
    ]
    name: LocalizedText
    description: LocalizedText | None = None
    price: Money
    term_days: int | None = None
    quota: dict[str, Any] | None = None
    """For SUBSCRIPTION — listing quotas/limits (BRULE-07)."""
