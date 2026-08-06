import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { requireAuth } from "@/lib/require-auth";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { PropertyCard } from "@/components/data/PropertyCard";
import { PropertyGridSkeleton } from "@/components/data/PropertyCardSkeleton";
import { EmptyState } from "@/components/state/EmptyState";
import { favoritePropertiesOptions } from "@/features/properties/favorites-queries";

// No SSR `loader` here on purpose: fetching favorites needs the session token, which only
// exists in the browser (sessionStorage) -- an SSR-time fetch would run unauthenticated and
// 500 the whole page (see require-auth.ts's own "Runs in the browser" note). Fetched
// client-side via useQuery instead, same as require-auth-guarded pages elsewhere.
export const Route = createFileRoute("/favorites")({
  beforeLoad: requireAuth,
  head: () => ({
    meta: [
      { title: "Favorites — ActiveHome" },
      { name: "description", content: "Properties you've saved across the platform." },
    ],
  }),
  component: Page,
});

function Page() {
  const { data: favorites, isLoading } = useQuery(favoritePropertiesOptions());
  return (
    <AppShell>
      <PageHeader eyebrow="Your collection" title="Favorites" description="Properties you've saved across the platform." />
      <div className="mx-auto max-w-7xl px-6 py-12">
        {isLoading || !favorites ? (
          <PropertyGridSkeleton />
        ) : favorites.length === 0 ? (
          <EmptyState title="No favorites yet" description="Save properties you like and they'll show up here." />
        ) : (
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {favorites.map((p, i) => (
              <PropertyCard key={p.id} property={p} index={i} />
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}
