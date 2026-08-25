/**
 * Whether the left/right skyscraper sidebar ad columns should render -- default-off (`false`)
 * until the public `/public/feature-flags` read resolves, so a slow/failed fetch never flashes
 * the sidebars in; only an explicit `true` from the server ever shows them. Shared by
 * `GlobalAdSidebars.tsx` (AppShell-based inner pages) and `Hero.tsx`'s own separate inline copy
 * (homepage), the two places that render `HOMEPAGE_SIDEBAR_LEFT`/`RIGHT`.
 */
import { useQuery } from "@tanstack/react-query";
import { getFeatureFlags } from "@/lib/feature-flags-client";

export function useSkyscraperAdsEnabled(): boolean {
  const { data } = useQuery({
    queryKey: ["public", "feature-flags"],
    queryFn: getFeatureFlags,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
  return data?.skyscraperAdsEnabled === true;
}
