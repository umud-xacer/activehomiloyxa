import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Package, Loader2 } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { catalogClient, formatUzs, type CatalogListing } from "@/lib/catalog-client";

/** Matches the path `configuration/infrastructure/seed.py`'s `_seed_catalog_taxonomy` actually
 * seeds and `CategoryCarousel.tsx` links to -- was `/qurilish-mollari` (no category ever existed
 * at that path, so this page always rendered empty). */
const CATEGORY_PATH = "/qurilish-materiallari";

export const Route = createFileRoute("/materials")({
  head: () => ({
    meta: [
      { title: "Qurilish mollari — ActiveHome" },
      {
        name: "description",
        content: "Tasdiqlangan yetkazib beruvchilardan qurilish mollarini buyurtma qiling.",
      },
    ],
  }),
  component: Page,
});

function MaterialCard({ listing }: { listing: CatalogListing }) {
  return (
    <div className="group overflow-hidden rounded-2xl border border-border bg-card shadow-soft transition hover:-translate-y-1 hover:shadow-elevated">
      <div className="flex h-36 items-center justify-center bg-gradient-to-br from-primary/10 to-primary-glow/10 text-primary">
        <Package className="size-10" />
      </div>
      <div className="p-4">
        <h3 className="font-display text-base font-semibold text-foreground">{listing.title}</h3>
        <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{listing.description}</p>
        <div className="mt-3 flex items-center justify-between">
          <span className="font-display text-lg font-semibold text-foreground">
            {formatUzs(listing.price?.amount)}
          </span>
          {listing.attributes.unit != null && (
            <span className="text-xs text-muted-foreground">
              / {String(listing.attributes.unit)}
            </span>
          )}
        </div>
        {listing.attributes.brand != null && (
          <div className="mt-2 inline-flex items-center rounded-full bg-muted px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground">
            {String(listing.attributes.brand)}
          </div>
        )}
      </div>
    </div>
  );
}

function Page() {
  const { data: listings, isLoading } = useQuery({
    queryKey: ["catalog", "listings", CATEGORY_PATH],
    queryFn: () => catalogClient.listingsByCategoryPath(CATEGORY_PATH, 40),
  });

  return (
    <AppShell>
      <PageHeader
        eyebrow="Do'kon"
        title="Qurilish mollari"
        description="Mixdan sement va armaturagacha — tasdiqlangan yetkazib beruvchilardan."
      />
      <div className="mx-auto max-w-7xl px-4 pb-24 lg:px-8">
        {isLoading && (
          <div className="flex items-center gap-2 py-12 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Yuklanmoqda…
          </div>
        )}
        {!isLoading && listings?.length === 0 && (
          <p className="py-12 text-center text-sm text-muted-foreground">
            Hozircha bu bo'limda mahsulot yo'q.
          </p>
        )}
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {listings?.map((listing) => (
            <MaterialCard key={listing.id} listing={listing} />
          ))}
        </div>
      </div>
    </AppShell>
  );
}
