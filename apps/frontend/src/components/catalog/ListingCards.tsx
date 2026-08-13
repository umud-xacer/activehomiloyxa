/**
 * Premium listing cards for the non-property "directions" (goods, service-provider CVs, venues) --
 * extracted out of `routes/categories/$slug.tsx` so the listing detail page
 * (`routes/listing/$listingId.tsx`) and any future surface (search results, homepage rails) can
 * reuse exactly the same rendering instead of re-deriving it. Every card links through to the
 * public listing detail page -- before this, these cards rendered inert (no way to open a listing
 * from the category grid at all).
 */
import { Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Sofa, Wrench, Building2, Clock, MapPin } from "lucide-react";
import { http } from "@/lib/http";
import { formatUzs, type CatalogListing } from "@/lib/catalog-client";
import { FavoriteButton } from "@/components/data/FavoriteButton";

function listingHref(listing: CatalogListing) {
  return { to: "/listing/$listingId" as const, params: { listingId: listing.id } };
}

interface _MediaAssetResponse {
  id: string;
  url?: string | null;
  variants?: Array<{ kind: string; url: string }>;
}

/** Resolves the listing's first CLEAN image to a real delivery URL (preferring the THUMBNAIL
 * variant -- a card doesn't need the full-size OPTIMIZED asset). A listing's `images` carry only
 * `mediaAssetId` (X-06: "catalog holds MediaAssetRef only"), never a URL directly, so this is a
 * per-card fetch, same as the listing detail page's own `resolveMediaUrls` -- react-query's
 * cache dedupes repeat requests for the same asset across cards. Returns `undefined` while
 * loading or when there is no clean image, both of which fall back to the icon placeholder. */
function useListingThumbnail(listing: CatalogListing): string | undefined {
  const image = listing.images?.find((img) => img.status === "CLEAN");
  const { data } = useQuery({
    queryKey: ["media-asset", image?.mediaAssetId],
    queryFn: () => http.get<_MediaAssetResponse>(`/media/${image!.mediaAssetId}`),
    enabled: image != null,
    staleTime: 5 * 60_000,
  });
  if (!data) return undefined;
  const thumbnail = data.variants?.find((v) => v.kind === "THUMBNAIL");
  return thumbnail?.url ?? data.url ?? undefined;
}

function CardThumbnail({ listing, Icon }: { listing: CatalogListing; Icon: typeof Sofa }) {
  const thumbnailUrl = useListingThumbnail(listing);
  if (thumbnailUrl) {
    return (
      <div className="h-32 overflow-hidden bg-muted">
        <img
          src={thumbnailUrl}
          alt={listing.title}
          className="size-full object-cover transition duration-300 group-hover:scale-105"
        />
      </div>
    );
  }
  return (
    <div className="flex h-32 items-center justify-center bg-gradient-to-br from-primary/10 to-primary-glow/10 text-primary">
      <Icon className="size-9" />
    </div>
  );
}

export function GoodsCard({ listing }: { listing: CatalogListing }) {
  return (
    <Link
      {...listingHref(listing)}
      className="group relative block overflow-hidden rounded-2xl border border-border bg-card shadow-soft transition hover:-translate-y-1 hover:shadow-elevated"
    >
      <FavoriteButton listingId={listing.id} className="absolute right-3 top-3 z-10" />
      <CardThumbnail listing={listing} Icon={Sofa} />
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
  const thumbnailUrl = useListingThumbnail(listing);
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
        <div className="size-12 shrink-0 overflow-hidden rounded-2xl bg-primary/10 text-primary">
          {thumbnailUrl ? (
            <img src={thumbnailUrl} alt={listing.title} className="size-full object-cover" />
          ) : (
            <div className="flex size-full items-center justify-center">
              <Wrench className="size-5" />
            </div>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
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
          <FavoriteButton listingId={listing.id} size="sm" variant="outline" />
        </div>
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
      className="group relative block overflow-hidden rounded-2xl border border-border bg-card shadow-soft transition hover:-translate-y-1 hover:shadow-elevated"
    >
      <FavoriteButton listingId={listing.id} className="absolute right-3 top-3 z-10" />
      <CardThumbnail listing={listing} Icon={Building2} />
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
