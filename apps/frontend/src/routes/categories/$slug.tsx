import { useMemo, useState } from "react";
import { createFileRoute, notFound, useNavigate, Link } from "@tanstack/react-router";
import { zodValidator, fallback } from "@tanstack/zod-adapter";
import { useSuspenseQuery, useQuery, useInfiniteQuery } from "@tanstack/react-query";
import { z } from "zod";
import { motion } from "framer-motion";
import {
  Map as MapIcon,
  Tag,
  Layers,
  Loader2,
  Clock,
  TrendingDown,
  TrendingUp,
  Sparkles,
  BadgePercent,
} from "lucide-react";
import { CategoryHub, type HubOption } from "@/components/catalog/CategoryHub";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { PropertyCard } from "@/components/data/PropertyCard";
import { PropertyGridSkeleton } from "@/components/data/PropertyCardSkeleton";
import { EmptyState } from "@/components/state/EmptyState";
import { ErrorState } from "@/components/state/ErrorState";
import { LeafletMapView, type MapMarker } from "@/components/map/LeafletMapView";
import { GoodsCard, ServiceCard, VenueCard } from "@/components/catalog/ListingCards";
import {
  CategoryFiltersSheet,
  applyListingFilters,
  emptyFilterState,
  type ListingFilterState,
} from "@/components/catalog/CategoryFilters";
import { TopCompanies, useTopCompanies } from "@/components/catalog/TopCompanies";
import { propertyListOptions } from "@/features/properties/queries";
import type { Property, PropertyQuery } from "@/features/properties/types";
import {
  catalogClient,
  formatUzs,
  type CategorySummary,
  type CatalogListing,
} from "@/lib/catalog-client";
import { categoryLabel } from "@/components/site/CategoryCarousel";
import { formatPriceWithUnit } from "@/lib/format";
import {
  listingKindOf,
  KIND_EYEBROW,
  KIND_ICON,
  KIND_THEME,
  type ListingKind,
} from "@/lib/listing-kind";

const searchSchema = z.object({
  sort: fallback(
    z.enum(["newest", "price_asc", "price_desc", "ai_score", "popular"]),
    "newest",
  ).default("newest"),
  page: fallback(z.number().int().min(1), 1).default(1),
});

export const Route = createFileRoute("/categories/$slug")({
  validateSearch: zodValidator(searchSchema),
  loaderDeps: ({ search }) => ({ sort: search.sort, page: search.page }),
  loader: async ({ context, params, deps }) => {
    const category = await catalogClient.categoryByPath(`/${params.slug}`);
    if (!category) throw notFound();

    const kind = listingKindOf(category);
    if (kind === "PROPERTY") {
      const query: PropertyQuery = {
        category_id: category.id,
        sort: deps.sort,
        page: deps.page,
        page_size: 24,
      };
      await context.queryClient.ensureQueryData(propertyListOptions(query));
    }
    return { category, kind };
  },
  head: ({ loaderData }) => {
    const name = loaderData?.category.name.uz_latn ?? "Kategoriya";
    return {
      meta: [
        { title: `${name} — ActiveHome` },
        { name: "description", content: `${name} bo'yicha barcha e'lonlar — ActiveHome.` },
      ],
    };
  },
  component: CategoryPage,
  pendingComponent: CategoryPending,
  errorComponent: ({ error, reset }) => <ErrorState error={error} reset={reset} />,
});

function CategoryPending() {
  return (
    <AppShell>
      <PageHeader eyebrow="Kategoriya" title="Yuklanmoqda..." />
      <div className="mx-auto max-w-7xl px-6 py-12">
        <PropertyGridSkeleton />
      </div>
    </AppShell>
  );
}

function categoryHref(path: string): string {
  return `/categories/${path.replace(/^\//, "")}`;
}

function ChildrenPills({ children }: { children: CategorySummary[] }) {
  if (children.length === 0) return null;
  return (
    <div className="mx-auto max-w-7xl px-6 pt-8">
      <div className="mb-3 flex items-center gap-2 text-sm font-medium text-muted-foreground">
        <Layers className="size-4" />
        Bo'lim ichidagi kichik kategoriyalar
      </div>
      <div className="flex flex-wrap gap-2">
        {children.map((child) => (
          <Link
            key={child.id}
            to={categoryHref(child.path)}
            className="rounded-full border border-border bg-card px-4 py-2 text-sm font-medium text-foreground/80 transition hover:border-primary/40 hover:text-foreground"
          >
            {categoryLabel(child.name, "uz")}
          </Link>
        ))}
      </div>
    </div>
  );
}

function useCategoryTree(categoryId: string, parentId: string | null) {
  const { data: allCategories = [] } = useQuery({
    queryKey: ["catalog", "categories", "all"],
    queryFn: () => catalogClient.listCategories(),
  });
  const children = allCategories.filter((c) => c.status === "ACTIVE" && c.parentId === categoryId);
  const parent = parentId ? allCategories.find((c) => c.id === parentId) : undefined;

  /** Full ancestor chain (root -> immediate parent), not just the one level `parent` gives --
   * an unlimited-depth category tree needs its whole path shown, not a single skipped level. */
  const byId = new Map(allCategories.map((c) => [c.id, c]));
  const ancestors: CategorySummary[] = [];
  let cursor = parentId ? byId.get(parentId) : undefined;
  const seen = new Set<string>();
  while (cursor && !seen.has(cursor.id)) {
    seen.add(cursor.id);
    ancestors.unshift(cursor);
    cursor = cursor.parentId ? byId.get(cursor.parentId) : undefined;
  }

  return { children, parent, ancestors };
}

/* ---------------------------------------------------------------------------------------------
 * PROPERTY -- the original real-estate flow (search-indexed listings, map, sort). Unchanged
 * behaviour from before this file learned about other directions.
 * ------------------------------------------------------------------------------------------- */

function buildMarkers(properties: Property[]): MapMarker[] {
  return properties.map((p) => ({
    id: p.id,
    lat: p.location.lat,
    lng: p.location.lng,
    label: formatPriceWithUnit(p.price, p.currency, p.listing_type),
    title: p.title,
    subtitle: [p.city, p.country].filter(Boolean).join(", "),
    image: p.media[0]?.url,
    href: `/properties/${p.slug}`,
  }));
}

const PROPERTY_HUB_OPTIONS: HubOption<PropertyQuery["sort"] & string>[] = [
  { value: "newest", label: "Yangi qo'shilganlar", icon: Clock },
  { value: "price_asc", label: "Arzon narxdan", icon: TrendingDown },
  { value: "price_desc", label: "Qimmat narxdan", icon: TrendingUp },
  { value: "ai_score", label: "Tavsiya etiladi", icon: Sparkles },
];

function PropertyDirectionView({ category }: { category: CategorySummary }) {
  const search = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const { children, ancestors } = useCategoryTree(category.id, category.parentId);
  const [featuredOnly, setFeaturedOnly] = useState(false);

  const query: PropertyQuery = {
    category_id: category.id,
    sort: search.sort,
    page: search.page,
    page_size: 24,
  };
  const { data } = useSuspenseQuery(propertyListOptions(query));
  const items = useMemo(
    () => (featuredOnly ? data.items.filter((p) => p.featured) : data.items),
    [data.items, featuredOnly],
  );

  const name = categoryLabel(category.name, "uz");
  const markers = useMemo(() => buildMarkers(items), [items]);
  const mapCenter = useMemo(() => {
    if (markers.length === 0) return { lat: 41.3111, lng: 69.2797 };
    const lat = markers.reduce((sum, m) => sum + m.lat, 0) / markers.length;
    const lng = markers.reduce((sum, m) => sum + m.lng, 0) / markers.length;
    return { lat, lng };
  }, [markers]);

  return (
    <AppShell>
      <PageHeader
        eyebrow="Kategoriya"
        title={name}
        description={`${data.total.toLocaleString()} ta e'lon — faqat "${name}" kategoriyasiga tegishli.`}
        crumbs={[
          { label: "Bosh sahifa", to: "/" },
          ...ancestors.map((a) => ({ label: categoryLabel(a.name, "uz"), to: categoryHref(a.path) })),
          { label: name },
        ]}
        backgroundImageUrl={category.heroImageUrl}
        accentColor={category.accentColor}
      />

      <ChildrenPills children={children} />

      <div className="mx-auto max-w-7xl px-6 pt-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CategoryHub
            options={PROPERTY_HUB_OPTIONS}
            value={search.sort}
            onChange={(sort) =>
              navigate({ search: (prev: typeof search) => ({ ...prev, sort, page: 1 }) })
            }
          />
          <button
            type="button"
            onClick={() => setFeaturedOnly((v) => !v)}
            className={`inline-flex items-center gap-2 rounded-2xl border px-4 py-2.5 text-sm font-medium shadow-soft transition ${
              featuredOnly
                ? "border-warning bg-warning/10 text-warning"
                : "border-border bg-card text-foreground/80 hover:border-warning/40"
            }`}
          >
            <BadgePercent className="size-4" />
            Chegirmadagilar
          </button>
        </div>
      </div>

      <div className="mx-auto max-w-7xl px-6 py-10">
        <div className="mb-8 flex flex-wrap items-center justify-between gap-4">
          <div className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-4 py-2 text-sm font-medium text-foreground/70">
            <Tag className="size-4" />
            {name}
            <span className="opacity-70">· {items.length} ta e'lon</span>
          </div>
        </div>

        {items.length === 0 ? (
          <EmptyState
            title="Bu kategoriyada hali e'lon yo'q"
            description="Tez orada shu kategoriyaga tegishli yangi e'lonlar paydo bo'ladi."
          />
        ) : (
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {items.map((p, i) => (
              <PropertyCard key={p.id} property={p} index={i} />
            ))}
          </div>
        )}
      </div>

      <section className="py-16">
        <div className="mx-auto max-w-7xl px-6">
          <div className="max-w-2xl">
            <div className="inline-flex items-center gap-2 rounded-full border border-border bg-card/60 px-3 py-1 text-[11px] font-medium uppercase tracking-widest text-foreground/70 backdrop-blur">
              <MapIcon className="size-3.5" />
              Jonli xarita
            </div>
            <h2 className="font-display mt-3 text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
              {name} — xaritada
            </h2>
            <p className="mt-3 text-base text-muted-foreground">
              Xaritada faqat "{name}" kategoriyasidagi e'lonlar ko'rsatilgan.
            </p>
          </div>

          <motion.div
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-100px" }}
            transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
            className="mt-10"
          >
            <LeafletMapView
              markers={markers}
              center={mapCenter}
              zoom={markers.length > 0 ? 7 : 6}
              height="540px"
              enableDrawTools={false}
            />
          </motion.div>
        </div>
      </section>
    </AppShell>
  );
}

/* ---------------------------------------------------------------------------------------------
 * GOODS / SERVICE / VENUE -- everything that isn't real estate. One shared data source
 * (`catalogClient.listingsByCategoryPath`, the same call `materials.tsx`/`furniture.tsx` already
 * use), three card renderings depending on `kind`.
 * ------------------------------------------------------------------------------------------- */

/** Builds map markers straight from catalog listings' own `location` (lat/lng) -- the same
 * `LeafletMapView` the PROPERTY direction already uses, so goods/service/venue categories get map
 * parity without a second map implementation (and without the API-key dependency an embedded
 * Yandex Maps widget would need -- see `LeafletMapView`'s own docstring on why this app stays on
 * keyless tiles after that exact failure mode took down a previous Google Maps integration).
 * Listings with no `location` are simply omitted -- not every goods/service listing carries one. */
function buildCatalogMarkers(listings: CatalogListing[]): MapMarker[] {
  return listings
    .filter((l) => l.location != null)
    .map((l) => ({
      id: l.id,
      lat: l.location!.latitude,
      lng: l.location!.longitude,
      label: formatUzs(l.price?.amount) || l.title,
      title: l.title,
      href: `/listing/${l.id}`,
    }));
}

type CatalogSort = "newest" | "price_asc" | "price_desc";

const CATALOG_HUB_OPTIONS: HubOption<CatalogSort>[] = [
  { value: "newest", label: "Yangi qo'shilganlar", icon: Clock },
  { value: "price_asc", label: "Arzon narxdan", icon: TrendingDown },
  { value: "price_desc", label: "Qimmat narxdan", icon: TrendingUp },
];

function sortListings(listings: CatalogListing[], sort: CatalogSort): CatalogListing[] {
  const withIndex = listings.map((l, i) => ({ l, i }));
  const priceOf = (l: CatalogListing) => {
    const n = Number(l.price?.amount);
    return Number.isFinite(n) ? n : null;
  };
  if (sort === "price_asc" || sort === "price_desc") {
    withIndex.sort((a, b) => {
      const pa = priceOf(a.l);
      const pb = priceOf(b.l);
      if (pa == null && pb == null) return a.i - b.i;
      if (pa == null) return 1;
      if (pb == null) return -1;
      return sort === "price_asc" ? pa - pb : pb - pa;
    });
  } else {
    withIndex.sort((a, b) => {
      const ta = Date.parse(a.l.createdAt);
      const tb = Date.parse(b.l.createdAt);
      return (Number.isFinite(tb) ? tb : 0) - (Number.isFinite(ta) ? ta : 0);
    });
  }
  return withIndex.map((x) => x.l);
}

function CatalogDirectionView({
  category,
  kind,
}: {
  category: CategorySummary;
  kind: Exclude<ListingKind, "PROPERTY">;
}) {
  const { children, ancestors } = useCategoryTree(category.id, category.parentId);
  const name = categoryLabel(category.name, "uz");
  const Icon = KIND_ICON[kind];
  const theme = KIND_THEME[kind];
  const [filters, setFilters] = useState<ListingFilterState>(emptyFilterState());
  const [sort, setSort] = useState<CatalogSort>("newest");
  const [selectedCompanyId, setSelectedCompanyId] = useState<string | null>(null);

  const {
    data: listingPages,
    isLoading,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ["catalog", "listings", category.id],
    queryFn: ({ pageParam }) =>
      catalogClient.listingsPageByCategoryId(category.id, { cursor: pageParam, limit: 24 }),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.page.nextCursor,
  });
  const listings = useMemo(
    () => listingPages?.pages.flatMap((p) => p.items) ?? [],
    [listingPages],
  );

  const { data: form } = useQuery({
    queryKey: ["catalog", "category-form", category.id],
    queryFn: () => catalogClient.getCategoryForm(category.id),
  });

  const filtered = useMemo(() => applyListingFilters(listings, filters), [listings, filters]);
  const byCompany = useMemo(
    () =>
      selectedCompanyId ? filtered.filter((l) => l.ownerProfileId === selectedCompanyId) : filtered,
    [filtered, selectedCompanyId],
  );
  const sorted = useMemo(() => sortListings(byCompany, sort), [byCompany, sort]);
  const markers = useMemo(() => buildCatalogMarkers(sorted), [sorted]);
  const companies = useTopCompanies(filtered);

  return (
    <AppShell>
      <PageHeader
        eyebrow={KIND_EYEBROW[kind]}
        title={name}
        description={
          kind === "SERVICE"
            ? `Shu yo'nalishdagi xizmat ko'rsatuvchilarning e'lonlari — tajriba, hudud va narx bo'yicha solishtiring.`
            : `"${name}" kategoriyasidagi barcha e'lonlar.`
        }
        crumbs={[
          { label: "Bosh sahifa", to: "/" },
          ...ancestors.map((a) => ({ label: categoryLabel(a.name, "uz"), to: categoryHref(a.path) })),
          { label: name },
        ]}
        backgroundImageUrl={category.heroImageUrl}
        accentColor={category.accentColor}
      />

      <ChildrenPills children={children} />

      <div className="mx-auto max-w-7xl px-4 pt-8 lg:px-8">
        <CategoryHub options={CATALOG_HUB_OPTIONS} value={sort} onChange={setSort} />
      </div>

      <div className="mx-auto max-w-7xl px-4 py-10 pb-24 lg:px-8">
        <div className="mb-8 flex flex-wrap items-center justify-between gap-3">
          <div
            className={`inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium ${theme.badge}`}
          >
            <Icon className="size-4" />
            {name}
            {!isLoading && <span className="opacity-70">· {sorted.length} ta e'lon</span>}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {form && form.sections.length > 0 && (
              <CategoryFiltersSheet
                fields={form.sections.flatMap((s) => s.fields)}
                state={filters}
                onChange={setFilters}
                resultCount={filtered.length}
              />
            )}
          </div>
        </div>

        {isLoading && (
          <div className="flex items-center gap-2 py-12 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Yuklanmoqda…
          </div>
        )}

        {!isLoading && sorted.length === 0 && (
          <EmptyState
            title={
              listings.length > 0
                ? "Filtrga mos e'lon topilmadi"
                : "Bu kategoriyada hali e'lon yo'q"
            }
            description={
              listings.length > 0
                ? "Filtrlarni o'zgartirib qayta urinib ko'ring."
                : kind === "SERVICE"
                  ? "Tez orada bu yo'nalishda xizmat ko'rsatuvchilar ro'yxatdan o'tadi."
                  : "Tez orada shu kategoriyaga tegishli yangi e'lonlar paydo bo'ladi."
            }
          />
        )}

        {!isLoading && sorted.length > 0 && (
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {sorted.map((listing) =>
              kind === "SERVICE" ? (
                <ServiceCard key={listing.id} listing={listing} />
              ) : kind === "VENUE" ? (
                <VenueCard key={listing.id} listing={listing} />
              ) : (
                <GoodsCard key={listing.id} listing={listing} />
              ),
            )}
          </div>
        )}

        {hasNextPage && (
          <div className="mt-8 flex justify-center">
            <button
              type="button"
              onClick={() => fetchNextPage()}
              disabled={isFetchingNextPage}
              className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-6 py-2.5 text-sm font-medium text-foreground transition hover:border-primary/40 disabled:opacity-60"
            >
              {isFetchingNextPage && <Loader2 className="size-4 animate-spin" />}
              Ko'proq yuklash
            </button>
          </div>
        )}

        <TopCompanies
          companies={companies}
          selectedId={selectedCompanyId}
          onSelect={setSelectedCompanyId}
        />
      </div>

      {markers.length > 0 && (
        <section className="pb-20">
          <div className="mx-auto max-w-7xl px-4 lg:px-8">
            <div className="max-w-2xl">
              <div className="inline-flex items-center gap-2 rounded-full border border-border bg-card/60 px-3 py-1 text-[11px] font-medium uppercase tracking-widest text-foreground/70 backdrop-blur">
                <MapIcon className="size-3.5" />
                Jonli xarita
              </div>
              <h2 className="font-display mt-3 text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
                {name} — xaritada
              </h2>
              <p className="mt-2 text-sm text-muted-foreground">
                Joylashuvi ko'rsatilgan e'lonlar xaritada aks etadi.
              </p>
            </div>
            <div className="mt-8">
              <LeafletMapView markers={markers} zoom={11} height="480px" enableDrawTools={false} />
            </div>
          </div>
        </section>
      )}
    </AppShell>
  );
}

function CategoryPage() {
  const { category, kind } = Route.useLoaderData();
  if (kind === "PROPERTY") return <PropertyDirectionView category={category} />;
  return <CatalogDirectionView category={category} kind={kind} />;
}
