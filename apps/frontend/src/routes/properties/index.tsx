import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { zodValidator, fallback } from "@tanstack/zod-adapter";
import { useSuspenseQuery } from "@tanstack/react-query";
import { useState } from "react";
import { z } from "zod";
import { Map, SlidersHorizontal } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { PropertyCard } from "@/components/data/PropertyCard";
import { PropertyGridSkeleton } from "@/components/data/PropertyCardSkeleton";
import { EmptyState } from "@/components/state/EmptyState";
import { ErrorState } from "@/components/state/ErrorState";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
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
  minPrice: z.number().min(0).optional(),
  maxPrice: z.number().min(0).optional(),
});

export const Route = createFileRoute("/properties/")({
  validateSearch: zodValidator(searchSchema),
  loaderDeps: ({ search }) => ({
    listing: search.listing,
    sort: search.sort,
    page: search.page,
    q: search.q,
    minPrice: search.minPrice,
    maxPrice: search.maxPrice,
  }),
  loader: ({ context, deps }) => {
    const query: PropertyQuery = {
      q: deps.q || undefined,
      listing_type: deps.listing === "any" ? undefined : deps.listing,
      sort: deps.sort,
      page: deps.page,
      page_size: 24,
      min_price: deps.minPrice,
      max_price: deps.maxPrice,
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
    min_price: search.minPrice,
    max_price: search.maxPrice,
  };
  const { data } = useSuspenseQuery(propertyListOptions(query));
  const activeFilterCount = [search.minPrice, search.maxPrice].filter(
    (v) => v !== undefined,
  ).length;
  const [draftMinPrice, setDraftMinPrice] = useState(search.minPrice?.toString() ?? "");
  const [draftMaxPrice, setDraftMaxPrice] = useState(search.maxPrice?.toString() ?? "");
  const [filtersOpen, setFiltersOpen] = useState(false);

  const applyFilters = () => {
    setFiltersOpen(false);
    navigate({
      search: (prev: typeof search) => ({
        ...prev,
        page: 1,
        minPrice: draftMinPrice ? Number(draftMinPrice) : undefined,
        maxPrice: draftMaxPrice ? Number(draftMaxPrice) : undefined,
      }),
    });
  };

  const clearFilters = () => {
    setDraftMinPrice("");
    setDraftMaxPrice("");
    setFiltersOpen(false);
    navigate({
      search: (prev: typeof search) => ({
        ...prev,
        page: 1,
        minPrice: undefined,
        maxPrice: undefined,
      }),
    });
  };

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
            <Popover open={filtersOpen} onOpenChange={setFiltersOpen}>
              <PopoverTrigger asChild>
                <button className="inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:shadow-glow">
                  <SlidersHorizontal className="size-4" /> Filters
                  {activeFilterCount > 0 && (
                    <span className="ml-0.5 flex size-5 items-center justify-center rounded-full bg-primary-foreground text-[11px] font-bold text-primary">
                      {activeFilterCount}
                    </span>
                  )}
                </button>
              </PopoverTrigger>
              <PopoverContent align="end" className="w-80 space-y-4">
                <div>
                  <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Price range
                  </div>
                  <div className="flex items-center gap-2">
                    <input
                      type="number"
                      min={0}
                      placeholder="Min"
                      value={draftMinPrice}
                      onChange={(e) => setDraftMinPrice(e.target.value)}
                      className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm outline-none focus:border-primary"
                    />
                    <span className="text-muted-foreground">–</span>
                    <input
                      type="number"
                      min={0}
                      placeholder="Max"
                      value={draftMaxPrice}
                      onChange={(e) => setDraftMaxPrice(e.target.value)}
                      className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm outline-none focus:border-primary"
                    />
                  </div>
                </div>
                <div className="flex items-center justify-between pt-1">
                  <button
                    onClick={clearFilters}
                    className="text-sm font-medium text-muted-foreground hover:text-foreground"
                  >
                    Clear
                  </button>
                  <button
                    onClick={applyFilters}
                    className="rounded-full bg-primary px-4 py-1.5 text-sm font-semibold text-primary-foreground hover:shadow-glow"
                  >
                    Apply
                  </button>
                </div>
              </PopoverContent>
            </Popover>
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
