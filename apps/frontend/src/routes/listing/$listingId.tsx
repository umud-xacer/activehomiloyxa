/**
 * Public product/service/venue detail page -- the missing piece for the goods/service/venue
 * directions (`categories/$slug.tsx`'s `CatalogDirectionView`). Before this route existed, its
 * cards (`components/catalog/ListingCards.tsx`) had nowhere to link to; `/list/$listingId` is the
 * *seller's own edit form* (`requireAuth`-gated), not a public listing page. This is the "Product
 * Detail" surface: gallery, price, the category's own dynamic attributes rendered with their real
 * labels, a location map when the listing has one, a same-category "O'xshash e'lonlar" rail
 * (heuristic today -- same category minus this listing -- the one spot a real recommendation
 * ranking would plug in later), and a "contact seller" action wired to the real messaging API.
 */
import { useMemo, useState } from "react";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useQueries, useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Loader2, MapPin, MessageCircle, ImageOff, ChevronRight } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { ErrorState } from "@/components/state/ErrorState";
import { LeafletMapView, type MapMarker } from "@/components/map/LeafletMapView";
import { GoodsCard, ServiceCard, VenueCard } from "@/components/catalog/ListingCards";
import {
  catalogClient,
  formatUzs,
  type CatalogListing,
  type FormField,
} from "@/lib/catalog-client";
import { getMediaAssetUrl } from "@/lib/media-client";
import { messagingApi } from "@/lib/messaging-client";
import { useMe } from "@/features/auth/useAuth";
import { ApiError } from "@/lib/http";
import { categoryLabel } from "@/components/site/CategoryCarousel";
import { listingKindOf, KIND_ICON, KIND_EYEBROW } from "@/lib/listing-kind";

export const Route = createFileRoute("/listing/$listingId")({
  head: () => ({ meta: [{ title: "E'lon — ActiveHome" }] }),
  component: Page,
});

function useListingImages(listing: CatalogListing | undefined) {
  const images = listing?.images ?? [];
  const results = useQueries({
    queries: images.map((img) => ({
      queryKey: ["media-url", img.mediaAssetId],
      queryFn: () => getMediaAssetUrl(img.mediaAssetId),
      staleTime: 5 * 60_000,
    })),
  });
  return results.map((r) => r.data).filter((u): u is string => !!u);
}

function formatAttributeValue(field: FormField, value: unknown): string {
  if (value == null || value === "") return "—";
  if (field.fieldType === "boolean") return value ? "Ha" : "Yo'q";
  const values = Array.isArray(value) ? value.map(String) : [String(value)];
  if (field.options && field.options.length > 0) {
    const byValue = new Map(field.options.map((o) => [o.value, o.label.uz_latn ?? o.value]));
    return values.map((v) => byValue.get(v) ?? v).join(", ");
  }
  return values.join(", ");
}

function AttributesGrid({ listing, fields }: { listing: CatalogListing; fields: FormField[] }) {
  const rows = fields.filter((f) => listing.attributes[f.code] != null);
  if (rows.length === 0) return null;
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {rows.map((field) => (
        <div key={field.code} className="rounded-xl border border-border/70 bg-card/50 p-3">
          <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            {field.label.uz_latn ?? field.code}
          </div>
          <div className="mt-0.5 text-sm font-medium text-foreground">
            {formatAttributeValue(field, listing.attributes[field.code])}
          </div>
        </div>
      ))}
    </div>
  );
}

function SimilarListings({
  kind,
  listings,
  excludeId,
}: {
  kind: "GOODS" | "SERVICE" | "VENUE";
  listings: CatalogListing[];
  excludeId: string;
}) {
  const items = listings.filter((l) => l.id !== excludeId).slice(0, 4);
  if (items.length === 0) return null;
  return (
    <section className="mt-16">
      <h2 className="font-display text-xl font-semibold text-foreground">O'xshash e'lonlar</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Shu kategoriyadan tanlangan boshqa e'lonlar.
      </p>
      <div className="mt-5 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {items.map((listing) =>
          kind === "SERVICE" ? (
            <ServiceCard key={listing.id} listing={listing} />
          ) : kind === "VENUE" ? (
            <VenueCard key={listing.id} listing={listing} />
          ) : (
            <GoodsCard key={listing.id} listing={listing} />
          ),
        )}
      </div>
    </section>
  );
}

function Page() {
  const { listingId } = Route.useParams();
  const navigate = useNavigate();
  const { data: account } = useMe();

  const {
    data: listing,
    isLoading: listingLoading,
    error: listingError,
  } = useQuery({
    queryKey: ["catalog", "listing", listingId],
    queryFn: () => catalogClient.getListing(listingId),
    retry: false,
  });

  const { data: categories = [] } = useQuery({
    queryKey: ["catalog", "categories", "all"],
    queryFn: () => catalogClient.listCategories(),
  });
  const category = useMemo(
    () => categories.find((c) => c.id === listing?.categoryId),
    [categories, listing?.categoryId],
  );

  const { data: form } = useQuery({
    queryKey: ["catalog", "category-form", listing?.categoryId],
    queryFn: () => catalogClient.getCategoryForm(listing!.categoryId),
    enabled: !!listing,
  });

  const { data: similar = [] } = useQuery({
    queryKey: ["catalog", "listings", category?.path, "similar"],
    queryFn: () => catalogClient.listingsByCategoryPath(category!.path, 8),
    enabled: !!category,
  });

  const images = useListingImages(listing);

  const [contactBusy, setContactBusy] = useState(false);
  const [contactError, setContactError] = useState<string | null>(null);

  const contactSeller = async () => {
    if (!listing) return;
    if (!account) {
      navigate({ to: "/auth/sign-in" });
      return;
    }
    setContactBusy(true);
    setContactError(null);
    try {
      await messagingApi.startConversation(
        listing.id,
        `Salom! "${listing.title}" e'loni haqida qiziqyapman.`,
      );
      navigate({ to: "/messages" });
    } catch (err) {
      setContactError(err instanceof ApiError ? err.message : "Xabar yuborib bo'lmadi.");
    } finally {
      setContactBusy(false);
    }
  };

  if (listingError) {
    return <ErrorState error={listingError} reset={() => window.location.reload()} />;
  }

  if (listingLoading || !listing) {
    return (
      <AppShell>
        <div className="mx-auto max-w-6xl px-6 py-32 text-center text-sm text-muted-foreground">
          <Loader2 className="mx-auto mb-3 size-6 animate-spin" /> Yuklanmoqda…
        </div>
      </AppShell>
    );
  }

  const kind = category ? listingKindOf(category) : "GOODS";
  const catalogKind = kind === "PROPERTY" ? "GOODS" : kind;
  const KindIcon = KIND_ICON[catalogKind];
  const marker: MapMarker | null = listing.location
    ? {
        id: listing.id,
        lat: listing.location.latitude,
        lng: listing.location.longitude,
        label: formatUzs(listing.price?.amount) || listing.title,
        title: listing.title,
      }
    : null;

  return (
    <AppShell>
      <div className="mx-auto max-w-6xl px-4 pb-24 pt-28 lg:px-8">
        <nav className="mb-6 flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
          <Link to="/" className="hover:text-foreground">
            Bosh sahifa
          </Link>
          {category && (
            <>
              <ChevronRight className="size-3" />
              <Link
                to="/categories/$slug"
                params={{ slug: category.path.replace(/^\//, "") }}
                className="hover:text-foreground"
              >
                {categoryLabel(category.name, "uz")}
              </Link>
            </>
          )}
          <ChevronRight className="size-3" />
          <span className="text-foreground">{listing.title}</span>
        </nav>

        <div className="grid grid-cols-1 gap-10 lg:grid-cols-[1.6fr_1fr]">
          <div>
            {/* Gallery */}
            {images.length > 0 ? (
              <div className="grid grid-cols-4 gap-2 overflow-hidden rounded-3xl">
                <div className="col-span-4 aspect-[16/10] overflow-hidden bg-muted sm:col-span-3">
                  <img src={images[0]} alt={listing.title} className="size-full object-cover" />
                </div>
                <div className="col-span-4 grid grid-cols-4 gap-2 sm:col-span-1 sm:grid-cols-1">
                  {images.slice(1, 4).map((url, i) => (
                    <div key={i} className="aspect-square overflow-hidden bg-muted sm:aspect-auto">
                      <img src={url} alt="" className="size-full object-cover" />
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="flex aspect-[16/9] items-center justify-center rounded-3xl border border-dashed border-border bg-muted/40 text-muted-foreground">
                <ImageOff className="size-8" />
              </div>
            )}

            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5 }}
              className="mt-8"
            >
              {category && (
                <div className="mb-3 inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1 text-xs font-medium text-foreground/70">
                  <KindIcon className="size-3.5" />
                  {KIND_EYEBROW[catalogKind]}
                </div>
              )}
              <h1 className="font-display text-3xl font-semibold tracking-tight text-foreground">
                {listing.title}
              </h1>
              <div className="mt-3 font-display text-2xl font-semibold text-primary">
                {formatUzs(listing.price?.amount) || "Narx kelishiladi"}
              </div>
              {listing.description && (
                <p className="mt-5 whitespace-pre-line text-sm leading-relaxed text-muted-foreground">
                  {listing.description}
                </p>
              )}

              {form && form.sections.length > 0 && (
                <div className="mt-8 space-y-6">
                  {form.sections.map((section) => (
                    <div key={section.code}>
                      <h3 className="font-display mb-3 text-sm font-semibold text-foreground">
                        {section.label.uz_latn ?? section.code}
                      </h3>
                      <AttributesGrid listing={listing} fields={section.fields} />
                    </div>
                  ))}
                </div>
              )}
            </motion.div>

            {marker && (
              <section className="mt-10">
                <h2 className="font-display mb-4 text-lg font-semibold text-foreground">
                  Joylashuvi
                </h2>
                <LeafletMapView
                  markers={[marker]}
                  center={{ lat: marker.lat, lng: marker.lng }}
                  zoom={13}
                  height="360px"
                  enableDrawTools={false}
                  enableSearch={false}
                  showCountBadge={false}
                />
              </section>
            )}
          </div>

          {/* Contact sidebar */}
          <div>
            <div className="sticky top-28 rounded-3xl border border-border bg-card p-6 shadow-soft">
              <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                <MessageCircle className="size-4 text-primary" />
                E'lon egasi bilan bog'lanish
              </div>
              <p className="mt-2 text-xs text-muted-foreground">
                Xabar yuborsangiz, suhbat "Xabarlar" bo'limida ochiladi.
              </p>
              {contactError && (
                <p className="mt-3 rounded-xl bg-destructive/10 px-3 py-2 text-xs text-destructive">
                  {contactError}
                </p>
              )}
              <button
                type="button"
                onClick={contactSeller}
                disabled={contactBusy}
                className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground shadow-soft transition hover:shadow-glow disabled:opacity-60"
              >
                {contactBusy && <Loader2 className="size-4 animate-spin" />}
                Xabar yozish
              </button>
              {listing.location && (
                <div className="mt-4 flex items-center gap-1.5 text-xs text-muted-foreground">
                  <MapPin className="size-3.5" /> Xaritada joylashuvi mavjud
                </div>
              )}
            </div>
          </div>
        </div>

        {category && (
          <SimilarListings kind={catalogKind} listings={similar} excludeId={listing.id} />
        )}
      </div>
    </AppShell>
  );
}
