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
  "SUBSCRIPTION" | "PREMIUM" | "FEATURED" | "TOP_PLACEMENT" | "VERIFICATION" | "BANNER_PLACEMENT";

export interface Product {
  id: string;
  code: string;
  productType: ProductType;
  name: LocalizedText;
  description?: LocalizedText | null;
  price: Money;
  termDays?: number | null;
  quota?: Record<string, unknown> | null;
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
  "ACTIVE_SUBSCRIPTION" | "LISTING_PROMOTION" | "VERIFICATION_ELIGIBILITY" | "BANNER_SLOT_BOOKING";

export interface Entitlement {
  id: string;
  orderId?: string | null;
  entitlementType: EntitlementType;
  promotionKind?: "PREMIUM" | "FEATURED" | "TOP_PLACEMENT" | null;
  targetId?: string | null;
  validFrom: string;
  validUntil: string;
  activationState: "ACTIVE" | "EXPIRED" | "REVOKED";
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
};
