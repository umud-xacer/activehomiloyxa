import { useQuery } from "@tanstack/react-query";
import { GenericListingCard } from "@/components/data/GenericListingCard";
import { PropertyGridSkeleton } from "@/components/data/PropertyCardSkeleton";
import { EmptyState } from "@/components/state/EmptyState";
import { categoryListingsOptions } from "@/features/properties/category-listings-queries";

/** Generic real-data listing grid for the non-real-estate verticals (construction, services,
 * materials, furniture, jobs, landscape, interior, hostels, appliances, maintenance) -- these
 * categories carry a minimal generic form (condition/unit), not the real-estate attribute set,
 * so they render with a plain card instead of `PropertyCard`. */
export function CategoryListingsSection({ categoryPath }: { categoryPath: string }) {
  const { data, isLoading } = useQuery(categoryListingsOptions(categoryPath));

  if (isLoading || !data) {
    return (
      <div className="mx-auto max-w-7xl px-6 py-12">
        <PropertyGridSkeleton count={4} />
      </div>
    );
  }

  if (data.listings.length === 0) {
    return (
      <div className="mx-auto max-w-7xl px-6 py-12">
        <EmptyState title="No listings yet" description="Check back soon — this category is just getting started." />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl px-6 py-12">
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {data.listings.map((listing, i) => (
          <GenericListingCard key={listing.id} listing={listing} index={i} />
        ))}
      </div>
    </div>
  );
}
