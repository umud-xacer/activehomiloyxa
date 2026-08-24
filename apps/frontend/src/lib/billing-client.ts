/**
 * Billing API client — matches the "Billing"/"Administration" sections of
 * contracts/openapi.yaml (the real, already-implemented `billing` module — BC-08).
 * Products of `productType: "SUBSCRIPTION"` are the platform's weekly/monthly tariff plans
 * (Monetization task); orders/invoices are settled by operator confirmation, not an online
 * gateway (DEC-02) — `createOrder` returns an unpaid invoice, and the buyer waits for an admin
 * to confirm payment via `adminConfirmInvoicePayment` before the entitlement activates.
 */
import { http } from "./http";

export interface Money {
  amount: string;
  currency: string;
}

export interface LocalizedText {
  uz_latn?: string;
  uz_cyrl?: string;
  ru?: string;
  en?: string;
}

export type ProductType =
  | "SUBSCRIPTION"
  | "PREMIUM"
  | "FEATURED"
  | "TOP_PLACEMENT"
  | "VERIFICATION"
  | "BANNER_PLACEMENT"
  | "LISTING_PUBLICATION"
  | "LISTING_CREDIT_PACK";

export interface Product {
  id: string;
  code: string;
  productType: ProductType;
  name: LocalizedText;
  description?: LocalizedText | null;
  price: Money;
  termDays?: number | null;
  quota?: Record<string, unknown> | null;
  /** LISTING_PUBLICATION only -- a category-specific price override; null is the platform
   * default (listing paywall, 2026-08-23). */
  categoryId?: string | null;
}

/** GET /pricing-plans response shape (listing paywall, 2026-08-23) -- the Paywall Modal's own
 * 4 options come straight from this: `singleListing` for "Bir martalik joylash", each entry of
 * `creditPacks` for Start/Biznes/Unlim (distinguished by `code`). */
export interface PricingPlans {
  singleListing: Product | null;
  creditPacks: Product[];
}

export type OrderStatus = "PENDING" | "INVOICED" | "PAID" | "FULFILLED" | "CANCELLED";

export interface Order {
  id: string;
  purchaserProfileId: string;
  productId: string;
  targetType?: "PROFILE" | "LISTING" | "SLOT_BOOKING" | null;
  targetId?: string | null;
  amount: Money;
  status: OrderStatus;
  invoiceId?: string | null;
  createdAt: string;
}

export type InvoiceStatus = "ISSUED" | "PAID" | "VOID";

export interface Invoice {
  id: string;
  orderId: string;
  invoiceNumber: string;
  amount: Money;
  status: InvoiceStatus;
  issuedAt: string;
  paymentConfirmedAt?: string | null;
}

export type EntitlementType =
  | "ACTIVE_SUBSCRIPTION"
  | "LISTING_PROMOTION"
  | "VERIFICATION_ELIGIBILITY"
  | "BANNER_SLOT_BOOKING"
  | "LISTING_PUBLICATION"
  | "LISTING_CREDIT_BALANCE";

export interface Entitlement {
  id: string;
  orderId?: string | null;
  entitlementType: EntitlementType;
  promotionKind?: "PREMIUM" | "FEATURED" | "TOP_PLACEMENT" | null;
  targetId?: string | null;
  validFrom: string;
  validUntil: string;
  activationState: "ACTIVE" | "EXPIRED" | "REVOKED";
  /** LISTING_CREDIT_BALANCE only — null means unlimited for that type, "not applicable" for
   * every other type (2026-08-24). */
  remainingCredits?: number | null;
}

interface Page<T> {
  items: T[];
  page: { limit: number; nextCursor: string | null };
}

export const billingApi = {
  /** GET /products — public, no auth required. */
  listProducts(productType?: ProductType): Promise<Product[]> {
    return http.get<Product[]>("/products", { params: { productType } });
  },

  /** GET /pricing-plans — public, no auth required (listing paywall, 2026-08-23). `categoryId`
   * resolves a category-specific single-listing price override if one is seeded, else the
   * platform default. */
  getPricingPlans(categoryId?: string): Promise<PricingPlans> {
    return http.get<PricingPlans>("/pricing-plans", { params: { categoryId } });
  },

  listMyOrders(): Promise<Order[]> {
    return http.get<Page<Order>>("/orders", { params: { limit: 100 } }).then((p) => p.items);
  },

  /** POST /orders — the acting business profile buys a product; server freezes its current
   * price into the order (`ProductSnapshot`) and issues an unpaid invoice in the same call. */
  createOrder(input: {
    productId: string;
    targetType: "PROFILE" | "LISTING" | "SLOT_BOOKING";
    targetId?: string;
  }): Promise<Order> {
    return http.post<Order>(
      "/orders",
      { productId: input.productId, targetType: input.targetType, targetId: input.targetId },
      { idempotent: true },
    );
  },

  getOrder(orderId: string): Promise<Order> {
    return http.get<Order>(`/orders/${orderId}`);
  },

  getOrderInvoice(orderId: string): Promise<Invoice> {
    return http.get<Invoice>(`/orders/${orderId}/invoice`);
  },

  /** GET /me/entitlements — the acting profile's own entitlements (defaults to active-only). */
  listMyEntitlements(activeOnly = true): Promise<Entitlement[]> {
    return http.get<Entitlement[]>("/me/entitlements", { params: { activeOnly } });
  },

  /** Convenience read for the subscription dashboard: the most-recently-valid
   * ACTIVE_SUBSCRIPTION entitlement, active or not (unlike `listMyEntitlements`'s own default),
   * so an expired subscription still shows its last `validUntil` for the "renew" prompt. */
  async getSubscriptionEntitlement(): Promise<Entitlement | null> {
    const all = await http.get<Entitlement[]>("/me/entitlements", {
      params: { activeOnly: false },
    });
    const subs = all.filter((e) => e.entitlementType === "ACTIVE_SUBSCRIPTION");
    if (subs.length === 0) return null;
    return subs.reduce((latest, e) => (e.validUntil > latest.validUntil ? e : latest));
  },

  // -- admin (payment confirmation) ------------------------------------------------------------

  adminListInvoices(status?: InvoiceStatus): Promise<Invoice[]> {
    return http
      .get<Page<Invoice>>("/admin/billing/invoices", { params: { status, limit: 100 } })
      .then((p) => p.items);
  },

  confirmInvoicePayment(
    invoiceId: string,
    input: { confirmed: boolean; note?: string },
  ): Promise<Invoice> {
    return http.post<Invoice>(`/admin/billing/invoices/${invoiceId}/confirm-payment`, input);
  },

  /** GET /admin/billing/payment-providers/status (2026-08-24) — presence-only, never the
   * secrets themselves; backs `/admin/settings`'s read-only provider panel. */
  adminGetPaymentProviderStatus(): Promise<PaymentProviderStatus> {
    return http.get<PaymentProviderStatus>("/admin/billing/payment-providers/status");
  },

  /** GET /admin/billing/profiles/{id}/entitlements (2026-08-24) — `/admin/users`'s credit-
   * balance panel; an admin-chosen profile id, not the caller's own. */
  adminListProfileEntitlements(profileId: string): Promise<Entitlement[]> {
    return http.get<Entitlement[]>(`/admin/billing/profiles/${profileId}/entitlements`);
  },

  /** POST /admin/billing/profiles/{id}/grant-credits (2026-08-24) — grants `productId`'s
   * entitlement for free, via the real createOrder+confirmPayment path. No `targetId` grants
   * `profileId` itself credits (`/admin/users`); `targetType: "LISTING"` + `targetId` grants
   * that listing VIP/TOP promotion instead (`/admin/listings`). */
  adminGrantCredits(
    profileId: string,
    input: { productId: string; targetType?: "PROFILE" | "LISTING"; targetId?: string; note?: string },
  ): Promise<Invoice> {
    return http.post<Invoice>(`/admin/billing/profiles/${profileId}/grant-credits`, input);
  },
};

export interface PaymentProviderStatus {
  paymeConfigured: boolean;
  clickConfigured: boolean;
  mockEnabled: boolean;
  uzumAvailable: boolean;
}
