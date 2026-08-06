import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { PropertyCard } from "@/components/data/PropertyCard";
import { PropertyGridSkeleton } from "@/components/data/PropertyCardSkeleton";
import { EmptyState } from "@/components/state/EmptyState";
import { CategoryListingsSection } from "@/components/site/CategoryListingsSection";
import { propertyListOptions } from "@/features/properties/queries";
import type { PropertyKind } from "@/features/properties/types";

export const Route = createFileRoute("/categories/$slug")({
  head: () => ({ meta: [{ title: "Category — ActiveHome" }] }),
  component: CategoryPage,
});

const REAL_ESTATE_KIND: Record<string, PropertyKind> = {
  apartments: "apartment",
  houses: "house",
  cottages: "cottage",
  commercial: "commercial",
  land: "land",
  hotels: "hotel",
};

function RealEstateCategory({ slug }: { slug: string }) {
  const kind = REAL_ESTATE_KIND[slug];
  const { data, isLoading } = useQuery(propertyListOptions({ kind, page_size: 24 }));

  if (isLoading || !data) {
    return (
      <div className="mx-auto max-w-7xl px-6 py-12">
        <PropertyGridSkeleton />
      </div>
    );
  }
  if (data.items.length === 0) {
    return (
      <div className="mx-auto max-w-7xl px-6 py-12">
        <EmptyState title="No listings yet" description="Check back soon for listings in this category." />
      </div>
    );
  }
  return (
    <div className="mx-auto max-w-7xl px-6 py-12">
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {data.items.map((p, i) => (
          <PropertyCard key={p.id} property={p} index={i} />
        ))}
      </div>
    </div>
  );
}

function CategoryPage() {
  const { slug } = Route.useParams();
  const title = slug.replace(/-/g, " ").replace(/\b\w/g, (c: string) => c.toUpperCase());
  const isRealEstate = slug in REAL_ESTATE_KIND;

  return (
    <AppShell>
      <PageHeader
        eyebrow="Category"
        title={title}
        description={`Premium ${title.toLowerCase()} from across the network.`}
        crumbs={[{ label: "Categories", to: "/categories" }, { label: title }]}
      />
      {isRealEstate ? <RealEstateCategory slug={slug} /> : <CategoryListingsSection categoryPath={slug} />}
    </AppShell>
  );
}
