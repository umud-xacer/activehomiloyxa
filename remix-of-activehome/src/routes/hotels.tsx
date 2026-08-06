import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { PropertyCard } from "@/components/data/PropertyCard";
import { PropertyGridSkeleton } from "@/components/data/PropertyCardSkeleton";
import { EmptyState } from "@/components/state/EmptyState";
import { propertyListOptions } from "@/features/properties/queries";

export const Route = createFileRoute("/hotels")({
  loader: ({ context }) =>
    context.queryClient.ensureQueryData(propertyListOptions({ kind: "hotel", page_size: 24 })),
  head: () => ({
    meta: [
      { title: "Hotels — ActiveHome" },
      { name: "description", content: "Book premium stays worldwide with instant confirmation." },
    ],
  }),
  component: Page,
});

function Page() {
  const { data, isLoading } = useQuery(propertyListOptions({ kind: "hotel", page_size: 24 }));
  return (
    <AppShell>
      <PageHeader eyebrow="Stays" title="Hotels" description="Book premium stays worldwide with instant confirmation." />
      <div className="mx-auto max-w-7xl px-6 py-12">
        {isLoading || !data ? (
          <PropertyGridSkeleton />
        ) : data.items.length === 0 ? (
          <EmptyState title="No hotels yet" description="Check back soon for hotel listings." />
        ) : (
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {data.items.map((p, i) => (
              <PropertyCard key={p.id} property={p} index={i} />
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}
