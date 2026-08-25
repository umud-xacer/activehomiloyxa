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
import { useCallback, useEffect, useMemo, useState } from "react";
import Autoplay from "embla-carousel-autoplay";
import {
  Carousel,
  CarouselContent,
  CarouselItem,
  CarouselNext,
  CarouselPrevious,
  type CarouselApi,
} from "@/components/ui/carousel";
import { cn } from "@/lib/utils";
import {
  serveBanner,
  serveBanners,
  recordBannerImpression,
  recordBannerClick,
} from "@/lib/ads-client";
import { getMediaAssetUrl } from "@/lib/media-client";

export interface ResolvedBanner {
  campaignId: string;
  imageUrl: string;
  targetUrl: string | null;
}

/** Same "wait for the page to go idle, then a randomized stagger" 503-avoidance workaround
 * `useServedBanner` documents below -- exported so `use-in-feed-ads.ts` (native/in-feed cards)
 * doesn't need its own copy. */
export async function waitForIdlePageLoad(): Promise<void> {
  if (document.readyState !== "complete") {
    await new Promise<void>((resolve) => {
      window.addEventListener("load", () => resolve(), { once: true });
    });
  }
  await new Promise((r) => setTimeout(r, 1200 + Math.random() * 400));
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
      await waitForIdlePageLoad();
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

/** Carousel/native-variant sibling of `useServedBanner` -- resolves every eligible campaign for
 * the slot (up to `limit`) via `GET /banners/serve-many`, in the same priority order the single
 * `serveBanner` picks its winner from, each with its creative already resolved to a real image
 * URL. Records one impression per resolved banner up front (all of them are about to render as
 * carousel slides, unlike `NativeAdCard`'s own per-card impression timing for in-feed cards). */
function useServedBanners(slotKey: string, limit: number): ResolvedBanner[] {
  const [banners, setBanners] = useState<ResolvedBanner[]>([]);

  useEffect(() => {
    let cancelled = false;
    setBanners([]);
    (async () => {
      await waitForIdlePageLoad();
      if (cancelled) return;
      const { items } = await serveBanners(slotKey, limit).catch(() => ({ items: [] }));
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
      withImages.forEach((b) => recordBannerImpression(b.campaignId));
    })();
    return () => {
      cancelled = true;
    };
  }, [slotKey, limit]);

  return banners;
}

/** The `variant="carousel"` renderer -- same visual language as the homepage's own
 * `PromoCarousel` (rounded-3xl, shadow-elevated, max-w-7xl, Embla autoplay/dots/arrows) so a
 * real ad carousel reads as a sibling of that section, not a different, cheaper-looking widget.
 * A single eligible banner still renders inside the same premium container, just without
 * arrows/dots (nothing to page between); zero eligible banners renders nothing at all, same as
 * every other `AdSlot` variant. */
function AdCarousel({ banners }: { banners: ResolvedBanner[] }) {
  const [api, setApi] = useState<CarouselApi>();
  const [selected, setSelected] = useState(0);
  const multi = banners.length > 1;

  const opts = useMemo(() => ({ loop: multi, align: "start" as const }), [multi]);
  const plugins = useMemo(
    () => (multi ? [Autoplay({ delay: 5000, stopOnInteraction: true })] : []),
    [multi],
  );

  useEffect(() => {
    if (!api) return;
    const onSelect = () => setSelected(api.selectedScrollSnap());
    onSelect();
    api.on("select", onSelect);
    api.on("reInit", onSelect);
    return () => {
      api.off("select", onSelect);
      api.off("reInit", onSelect);
    };
  }, [api]);

  const scrollTo = useCallback((index: number) => api?.scrollTo(index), [api]);

  if (banners.length === 0) return null;

  return (
    <div className="px-6">
      <div className="mx-auto max-w-7xl">
        <Carousel setApi={setApi} opts={opts} plugins={plugins}>
          <CarouselContent className="-ml-0">
            {banners.map((banner) => (
              <CarouselItem key={banner.campaignId} className="basis-full pl-0">
                <div className="overflow-hidden rounded-3xl border border-border shadow-elevated transition hover:shadow-glow">
                  {banner.targetUrl ? (
                    <a
                      href={banner.targetUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={() => recordBannerClick(banner.campaignId)}
                    >
                      <img
                        src={banner.imageUrl}
                        alt=""
                        loading="lazy"
                        className="max-h-[70vh] w-full object-contain"
                      />
                    </a>
                  ) : (
                    <img
                      src={banner.imageUrl}
                      alt=""
                      loading="lazy"
                      className="max-h-[70vh] w-full object-contain"
                    />
                  )}
                </div>
              </CarouselItem>
            ))}
          </CarouselContent>

          {multi && (
            <>
              <CarouselPrevious className="left-4 border-none bg-background/80 backdrop-blur" />
              <CarouselNext className="right-4 border-none bg-background/80 backdrop-blur" />
            </>
          )}
        </Carousel>

        {multi && (
          <div className="mt-4 flex items-center justify-center gap-2">
            {banners.map((banner, i) => (
              <button
                key={banner.campaignId}
                type="button"
                aria-label={`${i + 1}-slaydga o'tish`}
                onClick={() => scrollTo(i)}
                className={cn(
                  "h-2 rounded-full transition-all",
                  i === selected ? "w-6 bg-primary" : "w-2 bg-border hover:bg-primary/50",
                )}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function AdSlot({
  slotKey,
  variant = "horizontal",
  limit = 6,
}: {
  slotKey: string;
  variant?: "horizontal" | "sidebar" | "carousel";
  /** `variant="carousel"` only -- how many eligible campaigns to pull as slides. */
  limit?: number;
}) {
  // Delegates to one of two child components rather than branching which hook this component
  // itself calls -- each child unconditionally calls exactly one fetch hook, so there's no
  // conditional-hook-call concern even though `variant` can differ across siblings.
  if (variant === "carousel") {
    return <AdCarouselSlot slotKey={slotKey} limit={limit} />;
  }
  return <AdSingleSlot slotKey={slotKey} variant={variant} />;
}

function AdCarouselSlot({ slotKey, limit }: { slotKey: string; limit: number }) {
  const banners = useServedBanners(slotKey, limit);
  return <AdCarousel banners={banners} />;
}

function AdSingleSlot({
  slotKey,
  variant,
}: {
  slotKey: string;
  variant: "horizontal" | "sidebar";
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
