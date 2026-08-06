import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Sofa, Loader2 } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/state/EmptyState";
import { catalogClient, formatUzs, type CatalogListing } from "@/lib/catalog-client";

/** Matches the "Mebel materiallari" category path already hardcoded on the homepage
 * (`CategoryCarousel.tsx`'s `ICON_BY_PATH["/mebel-materiallari"]`) and seeded, together with its
 * attribute form (brand/material/condition/color/warranty/delivery), by
 * `configuration/infrastructure/seed.py`'s `_seed_furniture_category`. */
const CATEGORY_PATH = "/mebel-materiallari";

const MATERIAL_LABEL: Record<string, string> = {
  wood: "Yog'och",
  metal: "Metall",
  fabric: "Gazlama",
  plastic: "Plastik",
  other: "Boshqa",
};

const CONDITION_LABEL: Record<string, string> = {
  new: "Yangi",
  used: "Ishlatilgan",
};

export const Route = createFileRoute("/furniture")({
  head: () => ({
    meta: [
      { title: "Mebel — ActiveHome" },
      {
        name: "description",
        content: "Dizaynerlik brendlari va mahalliy ishlab chiqaruvchilardan mebel tanlang.",
      },
    ],
  }),
  component: Page,
});

function FurnitureCard({ listing }: { listing: CatalogListing }) {
  const material =
    listing.attributes.material != null
      ? (MATERIAL_LABEL[String(listing.attributes.material)] ?? String(listing.attributes.material))
      : null;
  const condition =
    listing.attributes.condition != null
      ? (CONDITION_LABEL[String(listing.attributes.condition)] ??
        String(listing.attributes.condition))
      : null;

  return (
    <div className="group overflow-hidden rounded-2xl border border-border bg-card shadow-soft transition hover:-translate-y-1 hover:shadow-elevated">
      {/* `CatalogListing.images` carries only `{id, mediaAssetId, position, status}` -- no
          delivery `url` (that requires a separate `GET /media/{id}` per image, resolved by the
          media module at upload time; see `media-client.ts`). Matches `materials.tsx`'s same
          icon-placeholder pattern rather than guessing an asset URL shape. */}
      <div className="flex h-36 items-center justify-center bg-gradient-to-br from-primary/10 to-primary-glow/10 text-primary">
        <Sofa className="size-10" />
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
          {condition && <span className="text-xs text-muted-foreground">{condition}</span>}
        </div>
        {(listing.attributes.brand != null || material) && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {listing.attributes.brand != null && (
              <span className="inline-flex items-center rounded-full bg-muted px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground">
                {String(listing.attributes.brand)}
              </span>
            )}
            {material && (
              <span className="inline-flex items-center rounded-full bg-muted px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground">
                {material}
              </span>
            )}
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
        title="Mebel"
        description="Dizaynerlik brendlari va mahalliy ishlab chiqaruvchilardan mebel tanlang."
        crumbs={[{ label: "Bosh sahifa", to: "/" }, { label: "Mebel" }]}
      />
      <div className="mx-auto max-w-7xl px-4 pb-24 lg:px-8">
        {isLoading && (
          <div className="flex items-center gap-2 py-12 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Yuklanmoqda…
          </div>
        )}
        {!isLoading && listings?.length === 0 && (
          <EmptyState
            title="Hozircha bu bo'limda mahsulot yo'q"
            description="Tez orada mebel mahsulotlari shu yerda paydo bo'ladi."
          />
        )}
        {!isLoading && listings != null && listings.length > 0 && (
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {listings.map((listing) => (
              <FurnitureCard key={listing.id} listing={listing} />
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}
