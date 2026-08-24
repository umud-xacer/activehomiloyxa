/**
 * ADR-0010: Payme/Click checkout-URL builders. Both providers use a plain browser-redirect
 * checkout (no SDK, no client secret ever touches the frontend) -- the buyer is sent to the
 * provider's own hosted payment page, pays, and the provider calls the BACKEND webhook
 * (`billing/infrastructure/payment_gateway/webhook_routers.py`) server-to-server to confirm; this
 * module only builds the outbound redirect URL, it never talks to either provider's API directly.
 *
 * Same "missing provider key is an expected, recoverable state" convention as
 * `lib/social-auth.ts`'s `getGoogleClientId()`/`getAppleClientId()`: until real merchant
 * credentials are configured (`VITE_PAYME_MERCHANT_ID`/`VITE_CLICK_SERVICE_ID`/
 * `VITE_CLICK_MERCHANT_ID`), the getters return null and the checkout buttons render an inline
 * "sozlanmagan" notice instead of redirecting to a gateway that would only reject the request.
 *
 * The `account`/`merchant_trans_id` reference sent to each provider is always our `Invoice.id`
 * (a UUID) -- matches `PaymeMerchantApi`/`ClickMerchantApi`'s own `account.invoice_id`/
 * `merchant_trans_id` convention exactly (`billing/infrastructure/payment_gateway/{payme,
 * click}.py`), so no extra Order lookup is needed on either side of the handshake.
 */
import { http } from "./http";
import type { Invoice } from "./billing-client";

export function getPaymeMerchantId(): string | null {
  const id = import.meta.env.VITE_PAYME_MERCHANT_ID as string | undefined;
  return id && id.trim().length > 0 ? id.trim() : null;
}

export function getClickServiceId(): string | null {
  const id = import.meta.env.VITE_CLICK_SERVICE_ID as string | undefined;
  return id && id.trim().length > 0 ? id.trim() : null;
}

export function getClickMerchantId(): string | null {
  const id = import.meta.env.VITE_CLICK_MERCHANT_ID as string | undefined;
  return id && id.trim().length > 0 ? id.trim() : null;
}

/** Where the buyer lands back on this site after paying (or cancelling) -- both providers just
 * redirect the browser here; the actual entitlement activation already happened server-to-server
 * via the webhook by the time this page re-renders (or the buyer polls/refreshes once). */
function returnUrl(): string {
  return `${window.location.origin}/subscriptions`;
}

/** Payme's checkout link is a base64-encoded `;`-joined `key=value` param string
 * (`m`=merchant id, `ac.invoice_id`=our account field, `a`=amount in TIYIN, `c`=return url,
 * `l`=UI language) appended to `https://checkout.paycom.uz/`. */
export function buildPaymeCheckoutUrl(merchantId: string, invoice: Invoice): string {
  const tiyin = Math.round(Number(invoice.amount.amount) * 100);
  const params = [
    `m=${merchantId}`,
    `ac.invoice_id=${invoice.id}`,
    `a=${tiyin}`,
    `c=${returnUrl()}`,
    "l=uz",
  ].join(";");
  return `https://checkout.paycom.uz/${btoa(params)}`;
}

/** Click's checkout link is a plain query string against `my.click.uz/services/pay` --
 * `transaction_param` is our `Invoice.id`, matching `ClickMerchantApi`'s `merchant_trans_id`. */
export function buildClickCheckoutUrl(
  serviceId: string,
  merchantId: string,
  invoice: Invoice,
): string {
  const params = new URLSearchParams({
    service_id: serviceId,
    merchant_id: merchantId,
    amount: invoice.amount.amount,
    transaction_param: invoice.id,
    return_url: returnUrl(),
  });
  return `https://my.click.uz/services/pay?${params.toString()}`;
}

/** Mock provider (listing paywall, 2026-08-23): `POST /payments/mock/pay` -- the one demo-only
 * endpoint that isn't a browser redirect like Payme/Click above, since there's no real gateway
 * to hand off to. Only reachable at all when the backend has `PAYMENT_PROVIDER=mock` set
 * (`composition_root.payment_provider_mode`'s own docstring) -- a 404 here means demo payments
 * are turned off, not a bug in this call. `providerLabel` is display-only (e.g. "UZUM", "PAYME",
 * "CLICK") -- which demo button the buyer clicked; it does not select a real provider. */
export async function mockPay(
  invoiceId: string,
  providerLabel: string,
): Promise<{ invoiceId: string; status: string }> {
  return http.post<{ invoiceId: string; status: string }>("/payments/mock/pay", {
    invoiceId,
    providerLabel,
  });
}
