import { Link } from "@tanstack/react-router";
import { motion } from "framer-motion";
import { Bath, BedDouble, MapPin, Maximize2, Sparkles, ShieldCheck } from "lucide-react";
import type { Property } from "@/features/properties/types";
import { formatArea } from "@/lib/format";
import { useDisplayPrice, formatDisplayPrice } from "@/lib/currency";
import { FavoriteButton } from "@/components/data/FavoriteButton";

interface Props {
  property: Property;
  index?: number;
}

/** Converts+formats `property.price` into the buyer's chosen display currency, preserving the
 * old `formatPriceWithUnit`'s "/mo"/"/night" suffix for rent/short_stay listings. */
function priceUnitSuffix(listingType: Property["listing_type"]): string {
  if (listingType === "rent") return " / mo";
  if (listingType === "short_stay") return " / night";
  return "";
}

export function PropertyCard({ property, index = 0 }: Props) {
  const cover = property.media[0]?.url;
  const { amount: displayAmount, currency: displayCurrency } = useDisplayPrice(
    property.price,
    property.currency,
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.6, delay: Math.min(index * 0.04, 0.4), ease: [0.22, 1, 0.36, 1] }}
      className="group relative overflow-hidden rounded-3xl border border-border bg-card shadow-soft transition-shadow hover:shadow-elevated"
    >
      <Link
        to="/properties/$slug"
        params={{ slug: property.id }}
        className="block"
        aria-label={property.title}
      >
        <div className="relative h-44 overflow-hidden sm:h-48">
          {cover && (
            <img
              src={cover}
              alt={property.title}
              loading="lazy"
              className="size-full object-cover transition-transform duration-700 group-hover:scale-[1.06]"
            />
          )}
          <div className="absolute inset-0 bg-gradient-to-t from-black/55 via-transparent to-transparent" />

          {/* Top badges */}
          <div className="absolute left-3 top-3 flex items-center gap-1.5">
            {property.verified && (
              <span className="inline-flex items-center gap-1 rounded-full bg-white/90 px-2 py-0.5 text-[11px] font-semibold text-foreground backdrop-blur">
                <ShieldCheck className="size-3 text-success" />
                Verified
              </span>
            )}
            <span className="inline-flex items-center gap-1 rounded-full bg-primary/90 px-2 py-0.5 text-[11px] font-semibold text-primary-foreground backdrop-blur">
              <Sparkles className="size-3" />
              AI {property.ai_score}
            </span>
          </div>

          <FavoriteButton listingId={property.id} className="absolute right-3 top-3" />

          {/* Price overlay */}
          <div className="absolute inset-x-3 bottom-3 flex items-end justify-between gap-2">
            <div>
              <div className="font-display text-lg font-semibold text-white drop-shadow">
                {displayAmount != null && formatDisplayPrice(displayAmount, displayCurrency)}
                {priceUnitSuffix(property.listing_type)}
              </div>
              {(property.city || property.country) && (
                <div className="flex items-center gap-1 text-[11px] text-white/80">
                  <MapPin className="size-3" />
                  {[property.city, property.country].filter(Boolean).join(", ")}
                </div>
              )}
            </div>
            <span className="rounded-full bg-white/15 px-2 py-0.5 text-[11px] font-medium uppercase tracking-wider text-white backdrop-blur">
              {property.listing_type === "sale"
                ? "For sale"
                : property.listing_type === "rent"
                  ? "Rent"
                  : "Stay"}
            </span>
          </div>
        </div>

        <div className="p-4">
          <h3 className="line-clamp-1 text-sm font-semibold text-foreground">{property.title}</h3>
          <p className="mt-1 line-clamp-1 text-xs text-muted-foreground">{property.address}</p>
          {(property.bedrooms > 0 || property.bathrooms > 0 || property.area_m2 > 0) && (
            <div className="mt-3 flex items-center gap-3 text-xs text-muted-foreground">
              {property.bedrooms > 0 && (
                <span className="inline-flex items-center gap-1">
                  <BedDouble className="size-3.5" /> {property.bedrooms}
                </span>
              )}
              {property.bathrooms > 0 && (
                <span className="inline-flex items-center gap-1">
                  <Bath className="size-3.5" /> {property.bathrooms}
                </span>
              )}
              {property.area_m2 > 0 && (
                <span className="inline-flex items-center gap-1">
                  <Maximize2 className="size-3.5" /> {formatArea(property.area_m2)}
                </span>
              )}
            </div>
          )}
        </div>
      </Link>
    </motion.div>
  );
}
