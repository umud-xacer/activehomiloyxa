import { useEffect, useMemo, useState } from "react";
import { createFileRoute, notFound, useNavigate, Link } from "@tanstack/react-router";
import { zodValidator, fallback } from "@tanstack/zod-adapter";
import { useSuspenseQuery, useQuery, useInfiniteQuery } from "@tanstack/react-query";
import { z } from "zod";
import { motion } from "framer-motion";
import {
  Map as MapIcon,
  Tag,
  Loader2,
  Clock,
  TrendingDown,
  TrendingUp,
  Sparkles,
  BadgePercent,
  Search as SearchIcon,
  X,
} from "lucide-react";
import { SortMenu, type HubOption } from "@/components/catalog/SortMenu";
import { SearchResultsPanel } from "@/components/search/SearchResultsPanel";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { PropertyCard } from "@/components/data/PropertyCard";
import { PropertyGridSkeleton } from "@/components/data/PropertyCardSkeleton";
import { EmptyState } from "@/components/state/EmptyState";
import { ErrorState } from "@/components/state/ErrorState";
import { YandexMapView, type MapMarker } from "@/components/map/YandexMapView";
import { GoodsCard, ServiceCard, VenueCard } from "@/components/catalog/ListingCards";
import {
  applyListingFilters,
  emptyFilterState,
  type ListingFilterState,
} from "@/components/catalog/CategoryFilters";
import { CategoryFilterPanel } from "@/components/catalog/CategoryFilterPanel";
import { CurrencySwitcher } from "@/components/catalog/CurrencySwitcher";
import { useDisplayCurrency, useUsdUzsRate, convertMoney } from "@/lib/currency";
import { TopCompanies, useTopCompanies } from "@/components/catalog/TopCompanies";
import { AdSlot } from "@/components/site/AdSlot";
import { Container } from "@/components/layout/Container";
import { apiClient } from "@/lib/api-client";
import { searchApi } from "@/lib/search-client";
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
  resolveListingKind,
  resolveAccentColor,
  resolveCategoryIcon,
  resolveHeroImage,
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

export const Route = createFileRoute("/categories/$")({
  validateSearch: zodValidator(searchSchema),
  loaderDeps: ({ search }) => ({ sort: search.sort, page: search.page }),
  loader: async ({ context, params, deps }) => {
    // NOTE: `allCategories` is deliberately NOT seeded into `context.queryClient` here (e.g. via
    // `ensureQueryData`) even though `useCategoryTree` below re-fetches the same data client-side
    // with a plain `useQuery` -- this app's router has no SSR/client query-cache dehydration
    // wiring (no `@tanstack/react-router-ssr-query`, no manual dehydrate/hydrate), so a
    // server-only-seeded plain `useQuery` renders full content in the SSR HTML but empty/loading
    // content on the client's first hydration pass, which is a genuine React hydration-mismatch
    // crash (confirmed live: reproducible on every category page load), not just a cosmetic
    // flash. `propertyListOptions` below gets away with the equivalent seed only because it's
    // read via `useSuspenseQuery`, which *suspends* instead of mismatching when the client cache
    // is empty (React's selective hydration treats a Suspense boundary pausing as expected, not
    // an error) -- `useCategoryTree`'s plain `useQuery` has no such protection.
    const [category, allCategories] = await Promise.all([
      catalogClient.categoryByPath(`/${params._splat}`),
      catalogClient.listCategories(),
    ]);
    if (!category) throw notFound();

    const kind = resolveListingKind(category, new Map(allCategories.map((c) => [c.id, c])));
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
      <Container wide className="py-12">
        <PropertyGridSkeleton />
      </Container>
    </AppShell>
  );
}

function categoryHref(path: string): string {
  return `/categories/${path.replace(/^\//, "")}`;
}

/** Builds the subcategory `<select>` options for `CategoryFilterPanel` from either this
 * category's real children (drilling down) or, for a leaf with none, its real siblings
 * (switching laterally) -- same real taxonomy data `ChildrenGrid` used to render as a chip row;
 * now it's the panel's first field instead of a separate block above it. */
function subcategorySelectProps({
  items,
  activeId,
  label,
  navigate,
}: {
  items: CategorySummary[];
  activeId?: string;
  label: string;
  navigate: (opts: { to: string }) => void;
}) {
  if (items.length === 0) return undefined;
  return {
    label,
    value: activeId ?? "",
    options: items.map((item) => ({ value: item.id, label: categoryLabel(item.name, "uz") })),
    onChange: (id: string) => {
      const target = items.find((item) => item.id === id);
      if (target) navigate({ to: categoryHref(target.path) });
    },
  };
}

function useCategoryTree(categoryId: string, parentId: string | null) {
  const { data: allCategories = [] } = useQuery({
    queryKey: ["catalog", "categories", "all"],
    queryFn: () => catalogClient.listCategories(),
  });
  const children = allCategories.filter((c) => c.status === "ACTIVE" && c.parentId === categoryId);
  const parent = parentId ? allCategories.find((c) => c.id === parentId) : undefined;

  /** Every category at the same level as this one (same `parentId`), current one included --
   * used as a fallback lateral-navigation strip when this category is a leaf (`children` is
   * empty), so a deep, childless subcategory doesn't strand the visitor with no way to see its
   * siblings ("Ofis binolari" hides "Omborxonalar"/"Do'konlar" otherwise). `null` at the root
   * (no meaningful "siblings of every top-level category" strip to show there). */
  const siblings = parentId
    ? allCategories.filter((c) => c.status === "ACTIVE" && c.parentId === parentId)
    : null;

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

  return { children, parent, siblings, ancestors, byId };
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
    href: `/properties/${p.id}`,
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
  const { children, siblings, ancestors, byId } = useCategoryTree(category.id, category.parentId);
  const [featuredOnly, setFeaturedOnly] = useState(false);
  // Real estate DOES have the same per-category dynamic-field system as goods/service/venue
  // (`catalogClient.getCategoryForm` works for any category id, real estate included -- confirmed
  // live: "Ko'p qavatli binolar" has real `rooms`/`condition`/`deal_type`/etc fields, each with a
  // `facetEligible` flag). But `FormField.facetEligible` and what `/search` actually enforces are
  // two SEPARATE admin-config entities that turned out to be out of sync in production: the
  // search module's own `filters[code]=value` handling silently drops any code not in that
  // category's *published* `SearchConfiguration.facet_field_codes` (`search/infrastructure/
  // opensearch_index.py`'s `_build_query_body`, gated on `facet_specs`) -- confirmed live by
  // sending `filters[condition]=<bogus value>` and getting the SAME result count back as no
  // filter at all. `GET /search/facets` is the one place that reflects the REAL, currently-
  // enforced facet set (empty for this category today, per that same live check -- no
  // `SearchConfiguration` has ever been published for it, a known gap: item 16 of the 2026-08-18
  // audit, "no admin UI for ... SEARCH_CONFIGURATION"). Intersecting against it here means this
  // panel only ever offers a real-estate filter control that actually filters something, instead
  // of a convincing-looking dropdown that silently does nothing.
  const { data: form } = useQuery({
    queryKey: ["catalog", "category-form", category.id],
    queryFn: () => catalogClient.getCategoryForm(category.id),
  });
  const { data: realFacets } = useQuery({
    queryKey: ["search", "facets", category.id],
    queryFn: () => searchApi.facets(category.id),
  });
  const facetFields = useMemo(() => {
    const enforced = new Set((realFacets ?? []).map((f) => f.fieldCode));
    return (form?.sections.flatMap((s) => s.fields) ?? []).filter((f) => enforced.has(f.code));
  }, [form, realFacets]);
  // `filterDraft` (what the inputs are bound to) is deliberately separate from `filterCommitted`
  // (what actually feeds `query`/`useSuspenseQuery` below): `useSuspenseQuery` re-suspends this
  // whole component -- including the `<input>`s themselves -- on every query-key change, so
  // wiring an input directly to `query` unmounted+remounted it on every keystroke, dropping focus
  // after the very first character typed (confirmed live: typing "100" into the price field only
  // ever committed "1"). Debouncing the commit lets typing/selecting itself stay
  // instant/uninterrupted while the real (suspending) query only fires once the user pauses.
  const [filterDraft, setFilterDraft] = useState<ListingFilterState>(emptyFilterState());
  const [filterCommitted, setFilterCommitted] = useState<ListingFilterState>(emptyFilterState());
  useEffect(() => {
    const t = setTimeout(() => setFilterCommitted(filterDraft), 500);
    return () => clearTimeout(t);
  }, [filterDraft]);
  const [displayCurrency] = useDisplayCurrency();
  const usdUzsRate = useUsdUzsRate();
  const hero = resolveHeroImage(category, byId);
  // A leaf category (no children of its own) falls back to showing its siblings, current one
  // highlighted, so lateral navigation never disappears just because a subcategory has no
  // further children of its own.
  const subcategoryItems = children.length > 0 ? children : (siblings ?? []);
  const subcategoryActiveId = children.length > 0 ? undefined : category.id;
  const subcategoryLabel =
    children.length > 0 ? "Bo'lim ichidagi kichik kategoriyalar" : "Shu turkumdagi bo'limlar";
  const subcategory = subcategorySelectProps({
    items: subcategoryItems,
    activeId: subcategoryActiveId,
    label: subcategoryLabel,
    navigate,
  });

  // `priceMin`/`priceMax` are typed in whatever currency the buyer currently has selected
  // (`displayCurrency`) -- converted to UZS here since `/search`'s `priceMin`/`priceMax` are
  // always interpreted as UZS (see `search/domain/query.py`'s `fx_usd_to_uzs` doc comment).
  // `fx_usd_to_uzs` is threaded through unconditionally (harmless when no price bound is set --
  // the backend only uses it alongside an actual bound) so a UZS-typed bound still correctly
  // matches a USD-priced listing and vice versa.
  const query: PropertyQuery = {
    category_id: category.id,
    sort: search.sort,
    page: search.page,
    page_size: 24,
    min_price: filterCommitted.priceMin
      ? convertMoney(Number(filterCommitted.priceMin), displayCurrency, "UZS", usdUzsRate)
      : undefined,
    max_price: filterCommitted.priceMax
      ? convertMoney(Number(filterCommitted.priceMax), displayCurrency, "UZS", usdUzsRate)
      : undefined,
    fx_usd_to_uzs: usdUzsRate,
    filters: Object.fromEntries(
      Object.entries(filterCommitted.attrs)
        .filter(([, v]) => v.length > 0)
        .map(([code, v]) => [code, v[0]]),
    ),
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
        tagline={hero.heroTagline}
        description={`${data.total.toLocaleString()} ta e'lon — faqat "${name}" kategoriyasiga tegishli.`}
        crumbs={[
          { label: "Bosh sahifa", to: "/" },
          ...ancestors.map((a) => ({
            label: categoryLabel(a.name, "uz"),
            to: categoryHref(a.path),
          })),
          { label: name },
        ]}
        backgroundImageUrl={hero.heroImageUrl}
        accentColor={resolveAccentColor(category, byId)}
        icon={resolveCategoryIcon(category)}
      />

      <Container wide className="pt-8 pb-2">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-4 py-2 text-sm font-medium text-foreground/70">
            <Tag className="size-4" />
            {name}
            <span className="opacity-70">· {items.length} ta e'lon</span>
          </div>
          <div className="flex items-center gap-2">
            <CurrencySwitcher />
            <SortMenu
              options={PROPERTY_HUB_OPTIONS}
              value={search.sort}
              onChange={(sort) =>
                navigate({ search: (prev: typeof search) => ({ ...prev, sort, page: 1 }) })
              }
              extra={{
                label: "Chegirmadagilar",
                icon: BadgePercent,
                active: featuredOnly,
                onToggle: () => setFeaturedOnly((v) => !v),
              }}
            />
          </div>
        </div>
      </Container>

      <Container wide className="pb-2">
        <CategoryFilterPanel
          fields={facetFields}
          state={filterDraft}
          onChange={setFilterDraft}
          showSellerKindTabs={false}
          subcategory={subcategory}
        />
      </Container>

      <Container wide className="py-8">
        {items.length === 0 && data.total === 0 ? (
          <EmptyState
            title="Bu kategoriyada hali e'lon yo'q"
            description="Tez orada shu kategoriyaga tegishli yangi e'lonlar paydo bo'ladi."
          />
        ) : items.length === 0 ? (
          <EmptyState
            title="Filtrga mos e'lon topilmadi"
            description="Boshqa sahifada yoki filtrsiz qidirib ko'ring."
          />
        ) : (
          <>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
              {items.map((p, i) => (
                <PropertyCard key={p.id} property={p} index={i} />
              ))}
            </div>
            <PropertyPager
              page={search.page}
              pageSize={data.page_size}
              total={data.total}
              onPageChange={(page) =>
                navigate({ search: (prev: typeof search) => ({ ...prev, page }) })
              }
            />
          </>
        )}
      </Container>

      <AdSlot slotKey="CATALOG_LIST_MID" />

      <section className="py-16">
        <Container wide>
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
            <YandexMapView
              markers={markers}
              center={mapCenter}
              zoom={markers.length > 0 ? 7 : 6}
              height="540px"
              enableDrawTools={false}
            />
          </motion.div>
        </Container>
      </section>
    </AppShell>
  );
}

function PropertyPager({
  page,
  pageSize,
  total,
  onPageChange,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  if (totalPages <= 1) return null;

  return (
    <div className="mt-10 flex items-center justify-center gap-3">
      <button
        type="button"
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
        className="rounded-full border border-border bg-card px-4 py-2 text-sm font-medium text-foreground disabled:opacity-40"
      >
        Oldingi
      </button>
      <span className="text-sm text-muted-foreground">
        {page} / {totalPages}
      </span>
      <button
        type="button"
        disabled={page >= totalPages}
        onClick={() => onPageChange(page + 1)}
        className="rounded-full border border-border bg-card px-4 py-2 text-sm font-medium text-foreground disabled:opacity-40"
      >
        Keyingi
      </button>
    </div>
  );
}

/* ---------------------------------------------------------------------------------------------
 * GOODS / SERVICE / VENUE -- everything that isn't real estate. One shared data source
 * (`catalogClient.listingsByCategoryPath`, the same call `materials.tsx`/`furniture.tsx` already
 * use), three card renderings depending on `kind`.
 * ------------------------------------------------------------------------------------------- */

interface CatalogSearchHit {
  id: string;
  title: string;
  categoryPath: string;
  price?: { amount: string; currency: string };
  location?: { latitude: number; longitude: number };
  thumbnailUrl?: string;
  slug?: string;
}

/** Builds map markers from `/search` hits (`apiClient.catalog.search`) -- richer than a bare
 * `/listings` row (image + price come free on the hit), and, via `categoryPathPrefix`, already
 * scoped to exactly this category's own subtree (a parent category's map aggregates every
 * descendant subcategory's listings; a leaf subcategory's map only ever gets its own, since
 * nothing sits deeper than it in the path). Listings with no `location` are simply omitted -- not
 * every goods/service listing carries one. */
function buildCatalogMarkers(hits: CatalogSearchHit[]): MapMarker[] {
  return hits
    .filter((h) => h.location != null)
    .map((h) => ({
      id: h.id,
      lat: h.location!.latitude,
      lng: h.location!.longitude,
      label: formatUzs(h.price?.amount) || h.title,
      title: h.title,
      image: h.thumbnailUrl,
      href: `/listing/${h.id}`,
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
  const navigate = useNavigate();
  const { children, siblings, ancestors, byId } = useCategoryTree(category.id, category.parentId);
  const hero = resolveHeroImage(category, byId);
  const name = categoryLabel(category.name, "uz");
  const subcategoryItems = children.length > 0 ? children : (siblings ?? []);
  const subcategoryActiveId = children.length > 0 ? undefined : category.id;
  const subcategoryLabel =
    children.length > 0 ? "Bo'lim ichidagi kichik kategoriyalar" : "Shu turkumdagi bo'limlar";
  const subcategory = subcategorySelectProps({
    items: subcategoryItems,
    activeId: subcategoryActiveId,
    label: subcategoryLabel,
    navigate,
  });
  const Icon = KIND_ICON[kind];
  const theme = KIND_THEME[kind];
  const [filters, setFilters] = useState<ListingFilterState>(emptyFilterState());
  const [sort, setSort] = useState<CatalogSort>("newest");
  const [displayCurrency] = useDisplayCurrency();
  const usdUzsRate = useUsdUzsRate();
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
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
  const listings = useMemo(() => listingPages?.pages.flatMap((p) => p.items) ?? [], [listingPages]);

  const { data: form } = useQuery({
    queryKey: ["catalog", "category-form", category.id],
    queryFn: () => catalogClient.getCategoryForm(category.id),
  });

  const filtered = useMemo(
    () => applyListingFilters(listings, filters, { displayCurrency, usdUzsRate }),
    [listings, filters, displayCurrency, usdUzsRate],
  );
  const byCompany = useMemo(
    () =>
      selectedCompanyId ? filtered.filter((l) => l.ownerProfileId === selectedCompanyId) : filtered,
    [filtered, selectedCompanyId],
  );
  const sorted = useMemo(() => sortListings(byCompany, sort), [byCompany, sort]);
  const companies = useTopCompanies(filtered);

  // Map markers come from a separate, subtree-aware `/search` query (`categoryPathPrefix`) rather
  // than the card feed's exact-match `listingsPageByCategoryId` above -- a parent category's map
  // should show every descendant subcategory's listings even though its own card grid (deliberately
  // unchanged here) only ever lists items tagged exactly to it.
  const { data: markerHits = [] } = useQuery({
    queryKey: ["catalog", "search", "map", category.path],
    queryFn: async () => {
      const page = await apiClient.catalog.search({
        categoryPathPrefix: category.path,
        limit: 200,
      });
      return page.items;
    },
  });
  const markers = useMemo(() => buildCatalogMarkers(markerHits), [markerHits]);

  return (
    <AppShell>
      <PageHeader
        eyebrow={KIND_EYEBROW[kind]}
        title={name}
        tagline={hero.heroTagline}
        description={
          kind === "SERVICE"
            ? `Shu yo'nalishdagi xizmat ko'rsatuvchilarning e'lonlari — tajriba, hudud va narx bo'yicha solishtiring.`
            : `"${name}" kategoriyasidagi barcha e'lonlar.`
        }
        crumbs={[
          { label: "Bosh sahifa", to: "/" },
          ...ancestors.map((a) => ({
            label: categoryLabel(a.name, "uz"),
            to: categoryHref(a.path),
          })),
          { label: name },
        ]}
        backgroundImageUrl={hero.heroImageUrl}
        accentColor={resolveAccentColor(category, byId)}
        icon={resolveCategoryIcon(category)}
      />

      <Container wide className="pt-8 pb-2">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div
            className={`inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium ${theme.badge}`}
          >
            <Icon className="size-4" />
            {name}
            {!isLoading && <span className="opacity-70">· {sorted.length} ta e'lon</span>}
          </div>
          <div className="flex items-center gap-2">
            <motion.div layout className="relative flex shrink-0 items-center">
              {searchOpen ? (
                <motion.div
                  initial={{ width: 36, opacity: 0 }}
                  animate={{ width: "auto", opacity: 1 }}
                  transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
                  className="flex items-center gap-1.5 overflow-hidden rounded-full border border-primary bg-card py-1.5 pl-3 pr-1.5"
                >
                  <SearchIcon className="size-4 shrink-0 text-primary" />
                  <input
                    autoFocus
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Escape") setSearchOpen(false);
                      if (e.key === "Enter" && searchQuery.trim()) {
                        setSearchOpen(false);
                        navigate({ to: "/search", search: { q: searchQuery.trim() } });
                      }
                    }}
                    placeholder="Shu kategoriyada qidirish"
                    className="w-40 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground/70 sm:w-56"
                  />
                  <button
                    type="button"
                    onClick={() => setSearchOpen(false)}
                    aria-label="Yopish"
                    className="flex size-6 shrink-0 items-center justify-center rounded-full text-muted-foreground transition hover:bg-secondary hover:text-foreground"
                  >
                    <X className="size-3.5" />
                  </button>
                </motion.div>
              ) : (
                <button
                  type="button"
                  onClick={() => setSearchOpen(true)}
                  aria-label="Shu kategoriyada qidirish"
                  className="flex size-9 shrink-0 items-center justify-center rounded-full border border-border text-foreground/70 transition hover:bg-secondary hover:text-foreground"
                >
                  <SearchIcon className="size-4" />
                </button>
              )}
              <SearchResultsPanel
                open={searchOpen}
                onOpenChange={setSearchOpen}
                categoryPathPrefix={category.path}
                externalQuery={searchQuery}
                onExternalQueryChange={setSearchQuery}
                className="absolute right-0 top-full z-50 mt-2 w-[calc(100vw-2rem)] max-w-md overflow-hidden rounded-2xl border border-slate-100 bg-card shadow-xl sm:w-[420px]"
              />
            </motion.div>
            <CurrencySwitcher />
            <SortMenu options={CATALOG_HUB_OPTIONS} value={sort} onChange={setSort} />
          </div>
        </div>
      </Container>

      <Container wide className="pb-2">
        <CategoryFilterPanel
          fields={form?.sections.flatMap((s) => s.fields) ?? []}
          state={filters}
          onChange={setFilters}
          subcategory={subcategory}
        />
      </Container>

      <Container wide className="py-8 pb-24">
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
                : "Bu kategoriyada to'g'ridan-to'g'ri e'lon yo'q"
            }
            description={
              listings.length > 0
                ? "Filtrlarni o'zgartirib qayta urinib ko'ring."
                : markers.length > 0
                  ? // Contradicts a populated map otherwise: `markers` is a subtree search
                    // (categoryPathPrefix) while `listings`/`sorted` are exact-category-only, so
                    // a parent with only subcategory listings would say "nothing here" right
                    // above a map full of pins.
                    "Lekin quyidagi bo'limlarda (pastdagi xaritada) tegishli e'lonlar mavjud."
                  : kind === "SERVICE"
                    ? "Tez orada bu yo'nalishda xizmat ko'rsatuvchilar ro'yxatdan o'tadi."
                    : "Tez orada shu kategoriyaga tegishli yangi e'lonlar paydo bo'ladi."
            }
          />
        )}

        {!isLoading && sorted.length > 0 && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
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
      </Container>

      <AdSlot slotKey="CATALOG_LIST_MID" />

      {markers.length > 0 && (
        <section className="pb-20">
          <Container wide>
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
              <YandexMapView markers={markers} zoom={11} height="480px" enableDrawTools={false} />
            </div>
          </Container>
        </section>
      )}
    </AppShell>
  );
}

function CategoryPage() {
  const { category, kind } = Route.useLoaderData();
  // `key={category.id}` forces a remount on every category-to-category navigation -- without
  // it, TanStack Router reuses the same component instance (same as React Router) and each
  // view's local `useState` (filters, sort, selectedCompanyId, featuredOnly) silently survives
  // into the new category, applying the previous category's filter state to it.
  if (kind === "PROPERTY") return <PropertyDirectionView category={category} key={category.id} />;
  return <CatalogDirectionView category={category} kind={kind} key={category.id} />;
}
