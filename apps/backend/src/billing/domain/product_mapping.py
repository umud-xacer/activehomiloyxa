"""billing -- the fixed ProductType -> (EntitlementType, required TargetType, PromotionKind)
mapping (Platform Capability [P], DDD Sec 5.8: "billing state machines" have fixed semantics).

No approved document enumerates this table literally -- it is, however, the ONLY defensible 1:1
correspondence between the closed `ProductType`s (`contracts/openapi.yaml Product.
productType`) and the closed `EntitlementType`s (Domain Model Sec 5.8's `EntitlementType [P]`
closed set): `SUBSCRIPTION`/`VERIFICATION`/`BANNER_PLACEMENT` map 1:1 onto `ACTIVE_SUBSCRIPTION`/
`VERIFICATION_ELIGIBILITY`/`BANNER_SLOT_BOOKING`, `PREMIUM`/`FEATURED`/`TOP_PLACEMENT` all
collapse onto `LISTING_PROMOTION` sub-typed by `promotion_kind`, and (added 2026-08-23 for the
listing paywall) `LISTING_PUBLICATION`/`LISTING_CREDIT_PACK` map 1:1 onto their own
`LISTING_PUBLICATION`/`LISTING_CREDIT_BALANCE` entitlement types -- every product type covered,
exactly zero entitlement types reachable two different ways.
`EntitlementFactory.activate_from_paid_order` (`billing/domain/entitlement.py`) is this table's
only reader. Flagged in `billing/README.md` "Known gaps" as an inferred-but-necessarily-unique
mapping, the same class of judgment call `search.interfaces.routers._field_code_label` already
documents for itself.

`REQUIRED_TARGET_TYPE` additionally fixes which `TargetType` each product requires
(`SUBSCRIPTION`/`VERIFICATION` target the purchaser's own profile; `PREMIUM`/`FEATURED`/
`TOP_PLACEMENT` target a listing; `BANNER_PLACEMENT` targets a slot booking window) --
`Order.create` enforces this pairing at construction time so an `EntitlementFactory` call against
an already-PAID order never has to re-validate it (Playbook Sec 6: validate once, at the
boundary, not defensively at every later read).
"""

from __future__ import annotations

from billing.domain.value_objects import (
    EntitlementType,
    ProductType,
    PromotionKind,
    TargetType,
)

ENTITLEMENT_TYPE_BY_PRODUCT: dict[ProductType, EntitlementType] = {
    ProductType.SUBSCRIPTION: EntitlementType.ACTIVE_SUBSCRIPTION,
    ProductType.PREMIUM: EntitlementType.LISTING_PROMOTION,
    ProductType.FEATURED: EntitlementType.LISTING_PROMOTION,
    ProductType.TOP_PLACEMENT: EntitlementType.LISTING_PROMOTION,
    ProductType.VERIFICATION: EntitlementType.VERIFICATION_ELIGIBILITY,
    ProductType.BANNER_PLACEMENT: EntitlementType.BANNER_SLOT_BOOKING,
    ProductType.LISTING_PUBLICATION: EntitlementType.LISTING_PUBLICATION,
    ProductType.LISTING_CREDIT_PACK: EntitlementType.LISTING_CREDIT_BALANCE,
}

REQUIRED_TARGET_TYPE_BY_PRODUCT: dict[ProductType, TargetType] = {
    ProductType.SUBSCRIPTION: TargetType.PROFILE,
    ProductType.PREMIUM: TargetType.LISTING,
    ProductType.FEATURED: TargetType.LISTING,
    ProductType.TOP_PLACEMENT: TargetType.LISTING,
    ProductType.VERIFICATION: TargetType.PROFILE,
    ProductType.BANNER_PLACEMENT: TargetType.SLOT_BOOKING,
    ProductType.LISTING_PUBLICATION: TargetType.LISTING,
    ProductType.LISTING_CREDIT_PACK: TargetType.PROFILE,
}

PROMOTION_KIND_BY_PRODUCT: dict[ProductType, PromotionKind] = {
    ProductType.PREMIUM: PromotionKind.PREMIUM,
    ProductType.FEATURED: PromotionKind.FEATURED,
    ProductType.TOP_PLACEMENT: PromotionKind.TOP_PLACEMENT,
}
