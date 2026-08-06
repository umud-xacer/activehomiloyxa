import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { zodValidator, fallback } from "@tanstack/zod-adapter";
import { useQuery, useSuspenseQuery } from "@tanstack/react-query";
import { z } from "zod";
import { Map, SlidersHorizontal } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { PropertyCard } from "@/components/data/PropertyCard";
import { PropertyGridSkeleton } from "@/components/data/PropertyCardSkeleton";
import { EmptyState } from "@/components/state/EmptyState";
import { ErrorState } from "@/components/state/ErrorState";
import { apiClient } from "@/lib/api-client";
import { categoriesOptions } from "@/features/properties/queries";
import type { SearchParams } from "@/lib/search-api";

const searchSchema = z.object({
  q: fallback(z.string(), "").default(""),
  category: fallback(z.string(), "").default(""),
  listing: fallback(z.enum(["sale", "rent", "short_stay", "any"]), "any").default("any"),
  sort: fallback(
    z.enum(["newest", "price_asc", "price_desc", "popular"]),
    "newest",
  ).default("newest"),
  bedrooms: fallback(z.string(), "").default(""),
  page: fallback(z.number().int().min(1), 1).default(1),
});

const SORT_TO_BACKEND: Record<string, SearchParams["sort"]> = {
  newest: "RECENCY",
  price_asc: "PRICE_ASC",
  price_desc: "PRICE_DESC",
  popular: "RELEVANCE",
};

const PAGE_SIZE = 24;

function searchOptionsFor(search: z.infer<typeof searchSchema>, categoryId?: string) {
  const filters: Record<string, string> = {};
  if (search.listing !== "any") filters.dealType = search.listing;
  if (search.bedrooms) filters.bedrooms = search.bedrooms;
  const params: SearchParams = {
    q: search.q || undefined,
    categoryId,
    sort: SORT_TO_BACKEND[search.sort],
    filters: Object.keys(filters).length ? filters : undefined,
    limit: PAGE_SIZE,
  };
  return {
    queryKey: ["properties", "search", params],
    queryFn: () => apiClient.properties.search(params),
    staleTime: 30_000,
  };
}

export const Route = createFileRoute("/properties/")({
  validateSearch: zodValidator(searchSchema),
  loaderDeps: ({ search }) => search,
  loader: async ({ context, deps }) => {
    const categories = await context.queryClient.ensureQueryData(categoriesOptions());
    const categoryId = categories.find((c) => c.path === deps.category)?.id;
    await context.queryClient.ensureQueryData(searchOptionsFor(deps, categoryId));
    return { categoryId };
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
      <PageHeader eyebrow="Discovery" title="Properties" description="Loading premium listings..." />
      <div className="mx-auto max-w-7xl px-6 py-12">
        <PropertyGridSkeleton />
      </div>
    </AppShell>
  );
}

function PropertiesPage() {
  const search = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const { data: categories } = useQuery(categoriesOptions());
  const categoryId = categories?.find((c) => c.path === search.category)?.id;
  const { data } = useSuspenseQuery(searchOptionsFor(search, categoryId));

  const bedroomsFacet = data.facets.find((f) => f.fieldCode === "bedrooms");
  const dealTypeFacet = data.facets.find((f) => f.fieldCode === "dealType");

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
        description={`${(data.total ?? data.items.length).toLocaleString()} verified listings across ${"10+"} countries.`}
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

      <div className="mx-auto max-w-7xl px-6 py-10">
        <div className="mb-8 flex flex-wrap items-center justify-between gap-4">
          <div className="inline-flex rounded-full border border-border bg-card p-1">
            {tabs.map((tab) => (
              <button
                key={tab.value}
                onClick={() =>
                  navigate({ search: (prev: typeof search) => ({ ...prev, listing: tab.value, page: 1 }) })
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
                search: (prev: typeof search) => ({ ...prev, sort: e.target.value as typeof search.sort, page: 1 }),
              })
            }
            className="rounded-full border border-border bg-card px-4 py-2 text-sm font-medium text-foreground"
          >
            <option value="newest">Newest</option>
            <option value="price_asc">Price · Low to high</option>
            <option value="price_desc">Price · High to low</option>
            <option value="popular">Most viewed</option>
          </select>
        </div>

        {(bedroomsFacet?.buckets.length || dealTypeFacet?.buckets.length) ? (
          <div className="mb-6 flex flex-wrap gap-4">
            {bedroomsFacet && bedroomsFacet.buckets.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-xs font-semibold text-muted-foreground">Xonalar:</span>
                {bedroomsFacet.buckets
                  .filter((b) => b.value)
                  .map((b) => (
                    <button
                      key={b.value}
                      onClick={() =>
                        navigate({
                          search: (prev: typeof search) => ({
                            ...prev,
                            bedrooms: prev.bedrooms === b.value ? "" : (b.value as string),
                            page: 1,
                          }),
                        })
                      }
                      className={`rounded-full border px-3 py-1 text-xs font-medium ${
                        search.bedrooms === b.value
                          ? "border-primary bg-primary text-primary-foreground"
                          : "border-border bg-card text-foreground/70 hover:text-foreground"
                      }`}
                    >
                      {b.value} ({b.count})
                    </button>
                  ))}
              </div>
            )}
          </div>
        ) : null}

        {data.items.length === 0 ? (
          <EmptyState title="No matching properties" description="Try widening your filters." />
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
