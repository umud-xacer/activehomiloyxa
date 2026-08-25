/**
 * Resolves the small pool of banners `NativeAdCard` interleaves into a listings/organizations
 * grid -- one `GET /banners/serve-many` call for the whole page (not one per card position), so
 * N in-feed ad slots never mean N independent requests. `count` should be
 * `Math.floor(items.length / every)` (see `interleaveAds`); if fewer real campaigns are eligible
 * than requested, fewer ad cards render -- `interleaveAds` only inserts a card at a position it
 * actually has a resolved banner for, never an empty placeholder.
 */
import { useEffect, useState } from "react";
import { serveBanners, recordBannerImpression } from "@/lib/ads-client";
import { getMediaAssetUrl } from "@/lib/media-client";
import { waitForIdlePageLoad, type ResolvedBanner } from "@/components/site/AdSlot";

export function useInFeedAds(slotKey: string, count: number): ResolvedBanner[] {
  const [banners, setBanners] = useState<ResolvedBanner[]>([]);

  useEffect(() => {
    if (count <= 0) {
      setBanners([]);
      return;
    }
    let cancelled = false;
    setBanners([]);
    (async () => {
      await waitForIdlePageLoad();
      if (cancelled) return;
      const { items } = await serveBanners(slotKey, count).catch(() => ({ items: [] }));
      if (items.length === 0 || cancelled) return;
      const resolved = await Promise.all(
        items.map(async (served) => {
          const imageUrl = await getMediaAssetUrl(served.creativeMediaAssetId);
          return imageUrl
            ? { campaignId: served.campaignId, imageUrl, targetUrl: served.targetUrl ?? null }
            : null;
        }),
      );
      if (cancelled) return;
      const withImages = resolved.filter((b): b is ResolvedBanner => b !== null);
      setBanners(withImages);
      // In-feed cards render immediately (no lazy/in-view gate, same as the rest of the grid's
      // own cards) so the impression is recorded up front, matching the carousel variant's timing.
      withImages.forEach((b) => recordBannerImpression(b.campaignId));
    })();
    return () => {
      cancelled = true;
    };
  }, [slotKey, count]);

  return banners;
}
