import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { zodValidator, fallback } from "@tanstack/zod-adapter";
import { useSuspenseQuery } from "@tanstack/react-query";
import { z } from "zod";
import { Map, SlidersHorizontal } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { PropertyCard } from "@/components/data/PropertyCard";
import { PropertyGridSkeleton } from "@/components/data/PropertyCardSkeleton";
import { EmptyState } from "@/components/state/EmptyState";
import { ErrorState } from "@/components/state/ErrorState";
import { propertyListOptions } from "@/features/properties/queries";
import type { PropertyQuery } from "@/features/properties/types";
import { Container } from "@/components/layout/Container";

const searchSchema = z.object({
  q: fallback(z.string(), "").default(""),
  listing: fallback(z.enum(["sale", "rent", "short_stay", "any"]), "any").default("any"),
  sort: fallback(
    z.enum(["newest", "price_asc", "price_desc", "ai_score", "popular"]),
    "newest",
  ).default("newest"),
  page: fallback(z.number().int().min(1), 1).default(1),
});

export const Route = createFileRoute("/properties/")({
  validateSearch: zodValidator(searchSchema),
  loaderDeps: ({ search }) => ({
    listing: search.listing,
    sort: search.sort,
    page: search.page,
    q: search.q,
  }),
  loader: ({ context, deps }) => {
    const query: PropertyQuery = {
      q: deps.q || undefined,
      listing_type: deps.listing === "any" ? undefined : deps.listing,
      sort: deps.sort,
      page: deps.page,
      page_size: 24,
    };
    return context.queryClient.ensureQueryData(propertyListOptions(query));
  },
  head: () => ({
    meta: [
      { title: "Properties — ActiveHome" },
      { name: "description", content: "Browse verified properties across the world." },
    ],
  }),
  component: PropertiesPage,
  pendingComponent: PropertiesPending,
  errorComponent: ({ error, reset }) => <ErrorState error={error} reset={reset} />,
});

function PropertiesPending() {
  return (
    <AppShell>
      <PageHeader
        eyebrow="Discovery"
        title="Properties"
        description="Loading premium listings..."
      />
      <Container wide className="py-12">
        <PropertyGridSkeleton />
      </Container>
    </AppShell>
  );
}

function PropertiesPage() {
  const search = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const query: PropertyQuery = {
    q: search.q || undefined,
    listing_type: search.listing === "any" ? undefined : search.listing,
    sort: search.sort,
    page: search.page,
    page_size: 24,
  };
  const { data } = useSuspenseQuery(propertyListOptions(query));

  const tabs: Array<{ value: typeof search.listing; label: string }> = [
    { value: "any", label: "All" },
    { value: "sale", label: "Buy" },
    { value: "rent", label: "Rent" },
    { value: "short_stay", label: "Stays" },
  ];

  return (
    <AppShell>
      <PageHeader
        eyebrow="Discovery"
        title="Properties"
        description={`${data.total.toLocaleString()} verified listings across ${"10+"} countries.`}
        actions={
          <>
            <Link
              to="/map"
              className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-4 py-2 text-sm font-semibold text-foreground hover:bg-muted"
            >
              <Map className="size-4" /> Map view
            </Link>
            <button className="inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:shadow-glow">
              <SlidersHorizontal className="size-4" /> Filters
            </button>
          </>
        }
      />

      <Container wide className="py-10">
        <div className="mb-8 flex flex-wrap items-center justify-between gap-4">
          <div className="inline-flex rounded-full border border-border bg-card p-1">
            {tabs.map((tab) => (
              <button
                key={tab.value}
                onClick={() =>
                  navigate({
                    search: (prev: typeof search) => ({ ...prev, listing: tab.value, page: 1 }),
                  })
                }
                className={`rounded-full px-4 py-1.5 text-sm font-medium transition ${
                  search.listing === tab.value
                    ? "bg-primary text-primary-foreground shadow-soft"
                    : "text-foreground/70 hover:text-foreground"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <select
            value={search.sort}
            onChange={(e) =>
              navigate({
                search: (prev: typeof search) => ({
                  ...prev,
                  sort: e.target.value as typeof search.sort,
                  page: 1,
                }),
              })
            }
            className="rounded-full border border-border bg-card px-4 py-2 text-sm font-medium text-foreground"
          >
            <option value="newest">Newest</option>
            <option value="price_asc">Price · Low to high</option>
            <option value="price_desc">Price · High to low</option>
            <option value="ai_score">AI score</option>
            <option value="popular">Most viewed</option>
          </select>
        </div>

        {data.items.length === 0 ? (
          <EmptyState title="No matching properties" description="Try widening your filters." />
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
            {data.items.map((p, i) => (
              <PropertyCard key={p.id} property={p} index={i} />
            ))}
          </div>
        )}
      </Container>
    </AppShell>
  );
}
