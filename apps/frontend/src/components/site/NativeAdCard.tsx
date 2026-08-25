/**
 * One in-feed ad card, interleaved into a listings/organizations grid via `interleaveAds` (see
 * `use-in-feed-ads.ts`) -- same `rounded-3xl border border-border bg-card shadow-soft` card
 * footprint as `PropertyCard`/`OrganizationCard` so it sits in the grid as a real card, not a
 * jarring full-width strip, but carries a small "Reklama" badge so it's never mistaken for a real
 * listing/organization. `object-contain` on a neutral tile (not `object-cover`) -- same reasoning
 * as `AdSlot`'s own image handling: an admin-uploaded creative can be any real proportion, and
 * `object-cover` would crop it unpredictably at this fixed card height.
 */
import { motion } from "framer-motion";
import { Megaphone } from "lucide-react";
import type { ResolvedBanner } from "@/components/site/AdSlot";
import { recordBannerClick } from "@/lib/ads-client";

export function NativeAdCard({ banner, index = 0 }: { banner: ResolvedBanner; index?: number }) {
  const onClick = () => recordBannerClick(banner.campaignId);

  const body = (
    <div className="relative flex h-44 items-center justify-center overflow-hidden bg-muted/40 sm:h-48">
      <img
        src={banner.imageUrl}
        alt=""
        loading="lazy"
        className="max-h-full max-w-full object-contain"
      />
      <span className="absolute left-3 top-3 inline-flex items-center gap-1 rounded-full bg-white/90 px-2 py-0.5 text-[11px] font-semibold text-foreground backdrop-blur">
        <Megaphone className="size-3" />
        Reklama
      </span>
    </div>
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.6, delay: Math.min(index * 0.04, 0.4), ease: [0.22, 1, 0.36, 1] }}
      className="group overflow-hidden rounded-3xl border border-border bg-card shadow-soft transition-shadow hover:shadow-elevated"
    >
      {banner.targetUrl ? (
        <a href={banner.targetUrl} target="_blank" rel="noopener noreferrer" onClick={onClick}>
          {body}
        </a>
      ) : (
        body
      )}
    </motion.div>
  );
}
