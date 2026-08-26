/**
 * Buyer-facing display-currency choice (so'm/UZS vs y.e./USD) + conversion helpers. A standalone
 * `useSyncExternalStore` module-level store rather than a React Context -- avoids touching
 * `__root.tsx` (currently only wraps `QueryClientProvider`) and sidesteps any SSR/hydration
 * concern from reading `localStorage` during render (the server snapshot is always "UZS", the
 * real stored choice takes over the first client render after hydration, same one-tick-late
 * pattern `useIsMobile` already uses for `window.matchMedia`).
 *
 * `price_min`/`price_max` sent to the backend, and every listing's own stored `price.currency`,
 * are the *source* currency -- this module only concerns the *display* choice layered on top.
 */
import { useSyncExternalStore } from "react";
import { useQuery } from "@tanstack/react-query";
import { getCurrencyRate } from "@/lib/currency-client";

export type DisplayCurrency = "UZS" | "USD";

const STORAGE_KEY = "activehome.display-currency";
const FALLBACK_USD_UZS_RATE = 12700;

const listeners = new Set<() => void>();
let currentCurrency: DisplayCurrency = "UZS";
let initialized = false;

function readStoredCurrency(): DisplayCurrency {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "USD" ? "USD" : "UZS";
  } catch {
    return "UZS";
  }
}

function ensureInitialized(): void {
  if (initialized || typeof window === "undefined") return;
  currentCurrency = readStoredCurrency();
  initialized = true;
}

function subscribe(listener: () => void): () => void {
  ensureInitialized();
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot(): DisplayCurrency {
  ensureInitialized();
  return currentCurrency;
}

function getServerSnapshot(): DisplayCurrency {
  return "UZS";
}

export function setDisplayCurrency(currency: DisplayCurrency): void {
  currentCurrency = currency;
  try {
    window.localStorage.setItem(STORAGE_KEY, currency);
  } catch {
    // private-window/blocked storage: the in-memory value above still drives this tab correctly,
    // it just won't persist across reloads.
  }
  for (const listener of listeners) listener();
}

/** The buyer's chosen display currency, persisted across visits. */
export function useDisplayCurrency(): [DisplayCurrency, (currency: DisplayCurrency) => void] {
  const currency = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  return [currency, setDisplayCurrency];
}

/** Live UZS-per-USD rate from `GET /public/currency-rate`, falling back to a sane default while
 * loading or on a failed fetch -- never blocks price display/filtering on the network round trip. */
export function useUsdUzsRate(): number {
  const { data } = useQuery({
    queryKey: ["public", "currency-rate"],
    queryFn: getCurrencyRate,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
  return data && data.usdUzsRate > 0 ? data.usdUzsRate : FALLBACK_USD_UZS_RATE;
}

/** Pure conversion. Any currency other than UZS/USD (rare, not asked for) passes through
 * unconverted rather than throwing -- this platform's own listings are only ever priced in one
 * of these two today. */
export function convertMoney(
  amount: number,
  from: string,
  to: DisplayCurrency,
  usdUzsRate: number,
): number {
  if (from === to) return amount;
  if (from === "UZS" && to === "USD") return amount / usdUzsRate;
  if (from === "USD" && to === "UZS") return amount * usdUzsRate;
  return amount;
}

/** Converts one listing's own price into the buyer's chosen display currency. Returns `undefined`
 * when there's no price to show at all (distinct from a real zero price). */
export function useDisplayPrice(
  amount: string | number | null | undefined,
  currency: string | null | undefined,
): { amount: number | undefined; currency: DisplayCurrency } {
  const [displayCurrency] = useDisplayCurrency();
  const rate = useUsdUzsRate();
  if (amount == null || currency == null) {
    return { amount: undefined, currency: displayCurrency };
  }
  const numericAmount = typeof amount === "string" ? Number(amount) : amount;
  if (Number.isNaN(numericAmount)) return { amount: undefined, currency: displayCurrency };
  return {
    amount: convertMoney(numericAmount, currency, displayCurrency, rate),
    currency: displayCurrency,
  };
}

/** `so'm`/`y.e.` formatting for an already-converted display amount -- pairs with
 * `useDisplayPrice`. Kept separate from `lib/format.ts`'s `formatCurrency` (real ISO currency
 * codes via `Intl.NumberFormat`) since "y.e." isn't a real ISO currency and needs its own label. */
export function formatDisplayPrice(amount: number, currency: DisplayCurrency): string {
  if (currency === "USD") {
    const fractionDigits = amount >= 1000 ? 0 : 2;
    return `${amount.toLocaleString("en-US", {
      minimumFractionDigits: fractionDigits,
      maximumFractionDigits: fractionDigits,
    })} y.e.`;
  }
  return `${Math.round(amount).toLocaleString("uz-UZ")} so'm`;
}
