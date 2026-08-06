import type { Currency, ListingType } from "@/features/properties/types";

/** Deliberately always "en-US" unless a caller opts into a different locale -- per-currency
 * "native" locales (uz-UZ, ru-RU, ar-AE, tr-TR) pull in currency-symbol CLDR data whose exact
 * spelling ("250 000 soʻm" vs "UZS 250,000") isn't guaranteed to match between the Node ICU
 * build doing SSR and the browser's own bundled ICU doing hydration -- a mismatch there is a
 * React hydration error on every price shown, not just a cosmetic difference. "en-US" is the
 * most consistently-implemented locale across ICU versions, and still renders the correct
 * currency symbol for major currencies (`style: "currency"` picks the symbol primarily from
 * `currency`, not `locale`). */
export function formatCurrency(amount: number, currency: Currency, locale = "en-US") {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency,
    maximumFractionDigits: amount >= 1000 ? 0 : 2,
  }).format(amount);
}

export function formatPriceWithUnit(
  amount: number,
  currency: Currency,
  listing: ListingType,
  locale?: string,
) {
  const price = formatCurrency(amount, currency, locale);
  if (listing === "rent") return `${price} / mo`;
  if (listing === "short_stay") return `${price} / night`;
  return price;
}

export function formatNumber(value: number, locale = "en-US") {
  return new Intl.NumberFormat(locale).format(value);
}

export function formatArea(m2: number) {
  return `${formatNumber(m2)} m²`;
}

export function formatRelativeDate(iso: string, locale = "en-US") {
  const date = new Date(iso);
  const diff = (date.getTime() - Date.now()) / 1000;
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  const abs = Math.abs(diff);
  if (abs < 60) return rtf.format(Math.round(diff), "second");
  if (abs < 3600) return rtf.format(Math.round(diff / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), "hour");
  if (abs < 86400 * 30) return rtf.format(Math.round(diff / 86400), "day");
  if (abs < 86400 * 365) return rtf.format(Math.round(diff / (86400 * 30)), "month");
  return rtf.format(Math.round(diff / (86400 * 365)), "year");
}
