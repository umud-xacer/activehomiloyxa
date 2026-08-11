/**
 * Renders one live banner placement, backed for real by `ads` module (apps/backend/src/ads/) --
 * `GET /banners/serve?slotKey=...` picks the eligible campaign (if any) for this slot, the
 * creative's image is resolved via `getMediaAssetUrl`, and an impression/click is recorded
 * through the same public/anonymous-safe `/banners/*` endpoints. Renders nothing (not even a
 * placeholder box) when there's no active campaign for the slot -- an idle ad slot should not
 * reserve visible layout space, same as how it behaves once a real campaign takes over.
 *
 * An admin creates the placement slot + campaign from `/$ownerAdminSlug/banners` -- the `slotKey`
 * passed in here must match one registered there exactly.
 */
import { useEffect, useState } from "react";
import { serveBanner, recordBannerImpression, recordBannerClick } from "@/lib/ads-client";
import { getMediaAssetUrl } from "@/lib/media-client";

interface ResolvedBanner {
  campaignId: string;
  imageUrl: string;
  targetUrl: string | null;
}

function useServedBanner(slotKey: string): ResolvedBanner | null {
  const [banner, setBanner] = useState<ResolvedBanner | null>(null);

  useEffect(() => {
    let cancelled = false;
    setBanner(null);
    (async () => {
      const served = await serveBanner(slotKey).catch(() => null);
      if (!served || cancelled) return;
      const imageUrl = await getMediaAssetUrl(served.creativeMediaAssetId);
      if (!imageUrl || cancelled) return;
      setBanner({
        campaignId: served.campaignId,
        imageUrl,
        targetUrl: served.targetUrl ?? null,
      });
      recordBannerImpression(served.campaignId);
    })();
    return () => {
      cancelled = true;
    };
  }, [slotKey]);

  return banner;
}

export function AdSlot({
  slotKey,
  variant = "horizontal",
}: {
  slotKey: string;
  variant?: "horizontal" | "sidebar";
}) {
  const banner = useServedBanner(slotKey);
  if (!banner) return null;

  const onClick = () => recordBannerClick(banner.campaignId);
  const image = (
    <img src={banner.imageUrl} alt="" className="size-full object-cover" loading="lazy" />
  );

  if (variant === "sidebar") {
    return (
      <div className="h-[420px] w-[160px] overflow-hidden rounded-2xl border border-border/70 bg-card/30">
        {banner.targetUrl ? (
          <a href={banner.targetUrl} target="_blank" rel="noopener noreferrer" onClick={onClick}>
            {image}
          </a>
        ) : (
          image
        )}
      </div>
    );
  }

  return (
    <div className="px-6">
      <div className="mx-auto h-24 max-w-7xl overflow-hidden rounded-2xl border border-border/70 bg-card/30 sm:h-28">
        {banner.targetUrl ? (
          <a href={banner.targetUrl} target="_blank" rel="noopener noreferrer" onClick={onClick}>
            {image}
          </a>
        ) : (
          image
        )}
      </div>
    </div>
  );
}
