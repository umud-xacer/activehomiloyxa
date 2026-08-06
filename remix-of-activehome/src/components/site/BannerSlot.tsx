import { useEffect, useRef, useState } from "react";
import { adsApi, type BannerServeView } from "@/lib/ads-api";
import { mediaAssetUrl } from "@/lib/media-api";

interface Props {
  slotKey: string;
  categoryId?: string;
  className?: string;
}

/**
 * Serves and renders one eligible banner for a slot. Records exactly one impression when the
 * banner first appears, and a click when tapped. Renders nothing (not even a placeholder) when
 * no banner is eligible (204) or on any error -- an empty slot must be invisible, never a broken
 * box, so ad availability never degrades the page layout.
 */
export function BannerSlot({ slotKey, categoryId, className }: Props) {
  const [banner, setBanner] = useState<BannerServeView | null>(null);
  const impressionRecorded = useRef(false);

  useEffect(() => {
    let cancelled = false;
    impressionRecorded.current = false;
    adsApi
      .serve({ slotKey, categoryId })
      .then((result) => {
        if (cancelled) return;
        setBanner(result);
        if (result && !impressionRecorded.current) {
          impressionRecorded.current = true;
          adsApi.recordImpression(result.campaignId).catch(() => {});
        }
      })
      .catch(() => {
        if (!cancelled) setBanner(null);
      });
    return () => {
      cancelled = true;
    };
  }, [slotKey, categoryId]);

  if (!banner) return null;

  const src = mediaAssetUrl(banner.creativeMediaAssetId, "optimized");

  return (
    <button
      type="button"
      onClick={() => adsApi.recordClick(banner.campaignId).catch(() => {})}
      className={`group relative block h-64 w-full overflow-hidden rounded-2xl border border-border bg-card shadow-soft transition hover:shadow-elevated sm:h-72 lg:h-80 ${className ?? ""}`}
      aria-label="Reklama"
    >
      {/* Blurred copy of the creative fills the slot's background so a portrait/odd-ratio image
          never leaves ugly empty bars -- the sharp, FULL creative sits on top via object-contain
          (whole image visible, never cropped). Standard "blur backdrop" ad-slot technique. */}
      <img
        src={src}
        alt=""
        aria-hidden
        className="absolute inset-0 size-full scale-110 object-cover opacity-40 blur-2xl"
      />
      <img
        src={src}
        alt="Reklama"
        loading="lazy"
        className="relative mx-auto h-full w-auto max-w-full object-contain drop-shadow-xl transition-transform duration-500 group-hover:scale-[1.02]"
      />
      <span className="absolute left-2 top-2 rounded-full bg-black/55 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-white/90 backdrop-blur">
        Reklama
      </span>
    </button>
  );
}
