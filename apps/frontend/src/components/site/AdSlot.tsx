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
      // Live repro + origin access-log correlation: every `/banners/serve` call made during the
      // initial page-load burst (while ~90 other asset/API requests are in flight on the same
      // freshly-opened connection) comes back 503 at the edge, even though uvicorn logs 204 for
      // the exact same request at the exact same timestamp -- the origin never sees a problem.
      // A 0-400ms stagger between the 5 slots alone did not fix it (still 503'd, just spread
      // out), so the trigger isn't slot-to-slot collision -- it's "early in a busy connection."
      // Waiting for the page to go fully idle (load event + a settle margin) before firing any
      // of them moves the request off that busy window entirely.
      if (document.readyState !== "complete") {
        await new Promise<void>((resolve) => {
          window.addEventListener("load", () => resolve(), { once: true });
        });
      }
      await new Promise((r) => setTimeout(r, 1200 + Math.random() * 400));
      if (cancelled) return;
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
  // Never a hardcoded aspect-ratio box -- an admin-uploaded creative can be any real proportion
  // (the actual seeded sidebar creatives are a tall 205x1024, nowhere near a 160:420 box; the
  // center one is 1920x544), and a fixed aspect-ratio container forces `object-cover` to crop
  // whatever doesn't match it. `h-auto` lets each container's height follow the image's own
  // intrinsic ratio at its fixed width instead, so nothing is ever cropped; `object-contain` is
  // a pure safety net for the (rare) case a `max-h` constraint below ever clips a very tall
  // upload -- it letterboxes rather than crops even then.
  const image = (
    <img src={banner.imageUrl} alt="" className="h-auto w-full object-contain" loading="lazy" />
  );

  if (variant === "sidebar") {
    // Fixed-width gutter (only ever shown on 2xl+ screens, see GlobalAdSidebars), height follows
    // the creative's own real aspect ratio -- capped so an unusually tall upload can't run past
    // the sticky container's own scroll-stop boundary and get visually clipped by it.
    return (
      <div className="max-h-[70vh] w-[160px] overflow-hidden rounded-2xl border border-border/70 bg-card/30">
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
      <div className="mx-auto max-h-[70vh] max-w-7xl overflow-hidden rounded-2xl border border-border/70 bg-card/30">
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
