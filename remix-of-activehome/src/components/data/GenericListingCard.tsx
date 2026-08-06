import { MapPin, Tag } from "lucide-react";
import { motion } from "framer-motion";
import type { BackendListing } from "@/lib/listing-api";

function formatPrice(listing: BackendListing): string {
  if (!listing.price) return "Narx kelishiladi";
  const amount = Number(listing.price.amount);
  return new Intl.NumberFormat("uz-UZ").format(amount) + " " + listing.price.currency;
}

export function GenericListingCard({ listing, index = 0 }: { listing: BackendListing; index?: number }) {
  return (
    <motion.article
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.6, delay: Math.min(index * 0.04, 0.4), ease: [0.22, 1, 0.36, 1] }}
      className="group relative overflow-hidden rounded-3xl border border-border bg-card p-5 shadow-soft transition-shadow hover:shadow-elevated"
    >
      <div className="flex items-start justify-between gap-3">
        <h3 className="line-clamp-2 text-sm font-semibold text-foreground">{listing.title}</h3>
        <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-semibold text-primary">
          <Tag className="size-3" />
          {formatPrice(listing)}
        </span>
      </div>
      {listing.description && (
        <p className="mt-2 line-clamp-2 text-xs text-muted-foreground">{listing.description}</p>
      )}
      {listing.location && (
        <div className="mt-3 inline-flex items-center gap-1 text-[11px] text-muted-foreground">
          <MapPin className="size-3" />
          {listing.location.latitude.toFixed(2)}, {listing.location.longitude.toFixed(2)}
        </div>
      )}
    </motion.article>
  );
}
