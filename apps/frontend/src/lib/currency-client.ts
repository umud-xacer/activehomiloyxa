/**
 * Public, unauthenticated currency-rate read -- `GET /public/currency-rate`, the fourth narrow
 * named-key exception to "no public read of platform-settings" (same shape as
 * `feature-flags-client.ts`'s `getFeatureFlags`). Backs the buyer-facing so'm/y.e. display
 * switcher and the /search price filter's currency-aware range.
 */
import { http } from "@/lib/http";

export interface CurrencyRate {
  usdUzsRate: number;
}

export async function getCurrencyRate(): Promise<CurrencyRate> {
  return http.get<CurrencyRate>("/public/currency-rate");
}
