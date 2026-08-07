/**
 * Premium listing cards for the non-property "directions" (goods, service-provider CVs, venues) --
 * extracted out of `routes/categories/$slug.tsx` so the listing detail page
 * (`routes/listing/$listingId.tsx`) and any future surface (search results, homepage rails) can
 * reuse exactly the same rendering instead of re-deriving it. Every card links through to the
 * public listing detail page -- before this, these cards rendered inert (no way to open a listing
 * from the category grid at all).
 */
import { Link } from "@tanstack/react-router";
import { Sofa, Wrench, Building2, Clock, MapPin } from "lucide-react";
import { formatUzs, type CatalogListing } from "@/lib/catalog-client";

function listingHref(listing: CatalogListing) {
  return { to: "/listing/$listingId" as const, params: { listingId: listing.id } };
}

export function GoodsCard({ listing }: { listing: CatalogListing }) {
  return (
    <Link
      {...listingHref(listing)}
      className="group block overflow-hidden rounded-2xl border border-border bg-card shadow-soft transition hover:-translate-y-1 hover:shadow-elevated"
    >
      <div className="flex h-32 items-center justify-center bg-gradient-to-br from-primary/10 to-primary-glow/10 text-primary">
        <Sofa className="size-9" />
      </div>
      <div className="p-4">
        <h3 className="font-display text-base font-semibold text-foreground">{listing.title}</h3>
        {listing.description && (
          <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{listing.description}</p>
        )}
        <div className="mt-3 flex items-center justify-between">
          <span className="font-display text-lg font-semibold text-foreground">
            {formatUzs(listing.price?.amount)}
          </span>
          {listing.attributes.condition != null && (
            <span className="text-xs text-muted-foreground">
              {String(listing.attributes.condition) === "new" ? "Yangi" : "Ishlatilgan"}
            </span>
          )}
        </div>
        {listing.attributes.brand != null && (
          <div className="mt-2 inline-flex items-center rounded-full bg-muted px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground">
            {String(listing.attributes.brand)}
          </div>
        )}
      </div>
    </Link>
  );
}

/** A service-provider's public "CV" -- experience/specialization/coverage/rate, whatever a
 * hiring business or household would actually filter a repairman/driver/truck-driver by.
 * Reads whichever trade-specific attribute (`trade`/`license_category`/`vehicle_type`) happens
 * to be present without hardcoding one particular trade's shape, since this card serves every
 * `xizmat-korsatish` child category. */
export function ServiceCard({ listing }: { listing: CatalogListing }) {
  const a = listing.attributes;
  const trade = a.trade ?? a.license_category ?? a.vehicle_type;
  const availableNow = a.available_now !== false;
  const rateLabel =
    a.rate_type === "hourly"
      ? "/soat"
      : a.rate_type === "daily"
        ? "/kun"
        : a.rate_type === "per_job"
          ? "/ish"
          : "";

  return (
    <Link
      {...listingHref(listing)}
      className="group block overflow-hidden rounded-2xl border border-border bg-card p-5 shadow-soft transition hover:-translate-y-1 hover:shadow-elevated"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex size-12 shrink-0 items-center justify-center rounded-2xl bg-primary/10 text-primary">
          <Wrench className="size-5" />
        </div>
        <span
          className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-medium ${
            availableNow ? "bg-success/10 text-success" : "bg-muted text-muted-foreground"
          }`}
        >
          <span
            className={`size-1.5 rounded-full ${availableNow ? "bg-success" : "bg-muted-foreground"}`}
          />
          {availableNow ? "Band emas" : "Band"}
        </span>
      </div>

      <h3 className="font-display mt-3 text-base font-semibold text-foreground">{listing.title}</h3>
      {listing.description && (
        <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{listing.description}</p>
      )}

      <div className="mt-3 flex flex-wrap gap-1.5">
        {a.specialization != null && (
          <span className="inline-flex items-center rounded-full bg-muted px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground">
            {String(a.specialization)}
          </span>
        )}
        {trade != null && (
          <span className="inline-flex items-center rounded-full bg-muted px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground">
            {String(trade)}
          </span>
        )}
        {a.experience_years != null && (
          <span className="inline-flex items-center rounded-full bg-muted px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground">
            {String(a.experience_years)} yil tajriba
          </span>
        )}
      </div>

      {a.service_regions != null && (
        <div className="mt-2.5 flex items-center gap-1.5 text-xs text-muted-foreground">
          <MapPin className="size-3.5 shrink-0" />
          <span className="truncate">{String(a.service_regions)}</span>
        </div>
      )}

      <div className="mt-3 flex items-center justify-between border-t border-border/60 pt-3">
        <span className="font-display text-lg font-semibold text-foreground">
          {formatUzs(listing.price?.amount)}
          <span className="text-xs font-normal text-muted-foreground">{rateLabel}</span>
        </span>
      </div>
    </Link>
  );
}

export function VenueCard({ listing }: { listing: CatalogListing }) {
  const a = listing.attributes;
  const priceUnitLabel =
    a.price_unit === "per_person"
      ? "kishi boshiga"
      : a.price_unit === "per_hour"
        ? "soatiga"
        : a.price_unit === "per_day"
          ? "kuniga"
          : "";

  return (
    <Link
      {...listingHref(listing)}
      className="group block overflow-hidden rounded-2xl border border-border bg-card shadow-soft transition hover:-translate-y-1 hover:shadow-elevated"
    >
      <div className="flex h-32 items-center justify-center bg-gradient-to-br from-primary/10 to-primary-glow/10 text-primary">
        <Building2 className="size-9" />
      </div>
      <div className="p-4">
        <h3 className="font-display text-base font-semibold text-foreground">{listing.title}</h3>
        {listing.description && (
          <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{listing.description}</p>
        )}
        <div className="mt-3 flex items-center justify-between">
          <span className="font-display text-lg font-semibold text-foreground">
            {formatUzs(listing.price?.amount)}
            {priceUnitLabel && (
              <span className="text-xs font-normal text-muted-foreground"> / {priceUnitLabel}</span>
            )}
          </span>
          {a.capacity != null && (
            <span className="text-xs text-muted-foreground">{String(a.capacity)} kishi</span>
          )}
        </div>
        {a.open_hours != null && (
          <div className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground">
            <Clock className="size-3.5 shrink-0" />
            {String(a.open_hours)}
          </div>
        )}
      </div>
    </Link>
  );
}
