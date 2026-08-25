/**
 * Public, unauthenticated feature-flag read -- `GET /public/feature-flags`, the narrow
 * named-key exception to "no public read of platform-settings" (same shape as
 * `platform-stats-client.ts`'s `getPlatformStats`). Currently backs exactly one flag: whether
 * the left/right "skyscraper" sidebar ad columns should render at all (default-off).
 */
import { http } from "@/lib/http";

export interface FeatureFlags {
  skyscraperAdsEnabled: boolean;
}

export async function getFeatureFlags(): Promise<FeatureFlags> {
  return http.get<FeatureFlags>("/public/feature-flags");
}
