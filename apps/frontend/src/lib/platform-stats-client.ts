/**
 * Homepage "proof strip" numbers -- combines two independent public sources rather than one
 * dedicated endpoint: `activeListings` is a real, live count read off `/search`'s own
 * `page.total` (already public, already accurate), while `cities`/`partners`/`satisfactionPercent`
 * have no live-computable source in the domain, so they come from `/public/platform-stats`
 * (configuration's `stats.*` settings keys, admin-editable, narrow named-key exception to "no
 * public read of platform-settings" -- same shape as `verifyOwnerAdminSlug`).
 */
import { http } from "@/lib/http";

export interface PlatformStats {
  activeListings: number;
  cities: number;
  partners: number;
  satisfactionPercent: number;
}

interface PlatformStatsSettingsResponse {
  cities: number;
  partners: number;
  satisfactionPercent: number;
}

interface SearchTotalResponse {
  page: { page: { total?: number | null } };
}

export async function getPlatformStats(): Promise<PlatformStats> {
  const [settings, search] = await Promise.all([
    http.get<PlatformStatsSettingsResponse>("/public/platform-stats"),
    http.get<SearchTotalResponse>("/search", { params: { limit: 1 } }),
  ]);
  return {
    activeListings: search.page?.page?.total ?? 0,
    cities: settings.cities,
    partners: settings.partners,
    satisfactionPercent: settings.satisfactionPercent,
  };
}
