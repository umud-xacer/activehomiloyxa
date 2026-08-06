import { useMemo } from "react";
import { createFileRoute, notFound, useNavigate, Link } from "@tanstack/react-router";
import { zodValidator, fallback } from "@tanstack/zod-adapter";
import { useSuspenseQuery, useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { motion } from "framer-motion";
import {
  Map as MapIcon,
  Tag,
  Layers,
  Loader2,
  Wrench,
  Building2,
  Sofa,
  Clock,
  MapPin,
} from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { PropertyCard } from "@/components/data/PropertyCard";
import { PropertyGridSkeleton } from "@/components/data/PropertyCardSkeleton";
import { EmptyState } from "@/components/state/EmptyState";
import { ErrorState } from "@/components/state/ErrorState";
import { LeafletMapView, type MapMarker } from "@/components/map/LeafletMapView";
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

/** Which shape a category's listings should be queried/rendered through. Everything not listed
 * here defaults to `"PROPERTY"` -- the original (and still the common) case, real estate served
 * via `/search` and force-fit into the `Property` shape (`catalog-client.ts`'s own docstring).
 * The other three kinds go straight at `catalogClient.listingsByCategoryPath` instead -- goods,
 * a service-provider's public "CV", and a venue, in that listing's own natural shape rather than
 * a real-estate one. Keyed by path the same way `CategoryCarousel.tsx`'s `ICON_BY_PATH` already
 * is -- keep both in sync if a seeded category's path ever changes
 * (`configuration/infrastructure/seed.py`'s `_seed_catalog_taxonomy` is the source of truth for
 * what's actually seeded). */
type ListingKind = "PROPERTY" | "GOODS" | "SERVICE" | "VENUE";

const CATEGORY_LISTING_KIND: Record<string, ListingKind> = {
  "/qurilish-materiallari": "GOODS",
  "/mebel-materiallari": "GOODS",
  "/maishiy-texnikalar": "GOODS",
  "/uy-bezaklari": "GOODS",
  "/uniforma-va-maxsus-kiyimlar": "GOODS",
  "/mebel-salonlari": "GOODS",
  "/hostel": "VENUE",
  "/mexmonxona": "VENUE",
  "/dam-olish-maskanlari": "VENUE",
  "/xizmat-korsatish": "SERVICE",
  "/tamirchi": "SERVICE",
  "/haydovchi": "SERVICE",
  "/yuk-haydovchi": "SERVICE",
  "/landshaft-dizayni": "SERVICE",
  "/ish-orni": "SERVICE",
};

function listingKindForPath(path: string): ListingKind {
  return CATEGORY_LISTING_KIND[path] ?? "PROPERTY";
}

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

    const kind = listingKindForPath(category.path);
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
  return { children, parent };
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

function PropertyDirectionView({ category }: { category: CategorySummary }) {
  const search = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const { children, parent } = useCategoryTree(category.id, category.parentId);

  const query: PropertyQuery = {
    category_id: category.id,
    sort: search.sort,
    page: search.page,
    page_size: 24,
  };
  const { data } = useSuspenseQuery(propertyListOptions(query));

  const name = categoryLabel(category.name, "uz");
  const markers = useMemo(() => buildMarkers(data.items), [data.items]);
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
          ...(parent
            ? [{ label: categoryLabel(parent.name, "uz"), to: categoryHref(parent.path) }]
            : []),
          { label: name },
        ]}
      />

      <ChildrenPills children={children} />

      <div className="mx-auto max-w-7xl px-6 py-10">
        <div className="mb-8 flex flex-wrap items-center justify-between gap-4">
          <div className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-4 py-2 text-sm font-medium text-foreground/70">
            <Tag className="size-4" />
            {name}
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
            <option value="newest">Yangi qo'shilganlar</option>
            <option value="price_asc">Narx: pastdan yuqoriga</option>
            <option value="price_desc">Narx: yuqoridan pastga</option>
            <option value="ai_score">AI bahosi</option>
            <option value="popular">Ko'p ko'rilgan</option>
          </select>
        </div>

        {data.items.length === 0 ? (
          <EmptyState
            title="Bu kategoriyada hali e'lon yo'q"
            description="Tez orada shu kategoriyaga tegishli yangi e'lonlar paydo bo'ladi."
          />
        ) : (
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {data.items.map((p, i) => (
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

const KIND_EYEBROW: Record<Exclude<ListingKind, "PROPERTY">, string> = {
  GOODS: "Do'kon",
  SERVICE: "Xizmat ko'rsatuvchilar",
  VENUE: "Dam olish",
};

const KIND_ICON: Record<Exclude<ListingKind, "PROPERTY">, typeof Sofa> = {
  GOODS: Sofa,
  SERVICE: Wrench,
  VENUE: Building2,
};

function GoodsCard({ listing }: { listing: CatalogListing }) {
  return (
    <div className="group overflow-hidden rounded-2xl border border-border bg-card shadow-soft transition hover:-translate-y-1 hover:shadow-elevated">
      <div className="flex h-32 items-center justify-center bg-gradient-to-br from-primary/10 to-primary-glow/10 text-primary">
        <Sofa className="size-9" />
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
          {listing.attributes.condition != null && (
            <span className="text-xs text-muted-foreground">
              {String(listing.attributes.condition) === "new" ? "Yangi" : "Ishlatilgan"}
            </span>
          )}
        </div>
        {listing.attributes.brand != null && (
          <div className="mt-2 inline-flex items-center rounded-full bg-muted px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground">
            {String(listing.attributes.brand)}
          </div>
        )}
      </div>
    </div>
  );
}

/** A service-provider's public "CV" -- experience/specialization/coverage/rate, whatever a
 * hiring business or household would actually filter a repairman/driver/truck-driver by.
 * Reads whichever trade-specific attribute (`trade`/`license_category`/`vehicle_type`) happens
 * to be present without hardcoding one particular trade's shape, since this card serves every
 * `xizmat-korsatish` child category. */
function ServiceCard({ listing }: { listing: CatalogListing }) {
  const a = listing.attributes;
  const trade = a.trade ?? a.license_category ?? a.vehicle_type;
  const availableNow = a.available_now !== false;
  const rateLabel =
    a.rate_type === "hourly"
      ? "/soat"
      : a.rate_type === "daily"
        ? "/kun"
        : a.rate_type === "per_job"
          ? "/ish"
          : "";

  return (
    <div className="group overflow-hidden rounded-2xl border border-border bg-card p-5 shadow-soft transition hover:-translate-y-1 hover:shadow-elevated">
      <div className="flex items-start justify-between gap-2">
        <div className="flex size-12 shrink-0 items-center justify-center rounded-2xl bg-primary/10 text-primary">
          <Wrench className="size-5" />
        </div>
        <span
          className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-medium ${
            availableNow ? "bg-success/10 text-success" : "bg-muted text-muted-foreground"
          }`}
        >
          <span
            className={`size-1.5 rounded-full ${availableNow ? "bg-success" : "bg-muted-foreground"}`}
          />
          {availableNow ? "Band emas" : "Band"}
        </span>
      </div>

      <h3 className="font-display mt-3 text-base font-semibold text-foreground">{listing.title}</h3>
      {listing.description && (
        <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{listing.description}</p>
      )}

      <div className="mt-3 flex flex-wrap gap-1.5">
        {a.specialization != null && (
          <span className="inline-flex items-center rounded-full bg-muted px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground">
            {String(a.specialization)}
          </span>
        )}
        {trade != null && (
          <span className="inline-flex items-center rounded-full bg-muted px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground">
            {String(trade)}
          </span>
        )}
        {a.experience_years != null && (
          <span className="inline-flex items-center rounded-full bg-muted px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground">
            {String(a.experience_years)} yil tajriba
          </span>
        )}
      </div>

      {a.service_regions != null && (
        <div className="mt-2.5 flex items-center gap-1.5 text-xs text-muted-foreground">
          <MapPin className="size-3.5 shrink-0" />
          <span className="truncate">{String(a.service_regions)}</span>
        </div>
      )}

      <div className="mt-3 flex items-center justify-between border-t border-border/60 pt-3">
        <span className="font-display text-lg font-semibold text-foreground">
          {formatUzs(listing.price?.amount)}
          <span className="text-xs font-normal text-muted-foreground">{rateLabel}</span>
        </span>
      </div>
    </div>
  );
}

function VenueCard({ listing }: { listing: CatalogListing }) {
  const a = listing.attributes;
  const priceUnitLabel =
    a.price_unit === "per_person"
      ? "kishi boshiga"
      : a.price_unit === "per_hour"
        ? "soatiga"
        : a.price_unit === "per_day"
          ? "kuniga"
          : "";

  return (
    <div className="group overflow-hidden rounded-2xl border border-border bg-card shadow-soft transition hover:-translate-y-1 hover:shadow-elevated">
      <div className="flex h-32 items-center justify-center bg-gradient-to-br from-primary/10 to-primary-glow/10 text-primary">
        <Building2 className="size-9" />
      </div>
      <div className="p-4">
        <h3 className="font-display text-base font-semibold text-foreground">{listing.title}</h3>
        {listing.description && (
          <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{listing.description}</p>
        )}
        <div className="mt-3 flex items-center justify-between">
          <span className="font-display text-lg font-semibold text-foreground">
            {formatUzs(listing.price?.amount)}
            {priceUnitLabel && (
              <span className="text-xs font-normal text-muted-foreground"> / {priceUnitLabel}</span>
            )}
          </span>
          {a.capacity != null && (
            <span className="text-xs text-muted-foreground">{String(a.capacity)} kishi</span>
          )}
        </div>
        {a.open_hours != null && (
          <div className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground">
            <Clock className="size-3.5 shrink-0" />
            {String(a.open_hours)}
          </div>
        )}
      </div>
    </div>
  );
}

function CatalogDirectionView({
  category,
  kind,
}: {
  category: CategorySummary;
  kind: Exclude<ListingKind, "PROPERTY">;
}) {
  const { children, parent } = useCategoryTree(category.id, category.parentId);
  const name = categoryLabel(category.name, "uz");
  const Icon = KIND_ICON[kind];

  const { data: listings, isLoading } = useQuery({
    queryKey: ["catalog", "listings", category.path],
    queryFn: () => catalogClient.listingsByCategoryPath(category.path, 40),
  });

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
          ...(parent
            ? [{ label: categoryLabel(parent.name, "uz"), to: categoryHref(parent.path) }]
            : []),
          { label: name },
        ]}
      />

      <ChildrenPills children={children} />

      <div className="mx-auto max-w-7xl px-4 py-10 pb-24 lg:px-8">
        <div className="mb-8 inline-flex items-center gap-2 rounded-full border border-border bg-card px-4 py-2 text-sm font-medium text-foreground/70">
          <Icon className="size-4" />
          {name}
        </div>

        {isLoading && (
          <div className="flex items-center gap-2 py-12 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Yuklanmoqda…
          </div>
        )}

        {!isLoading && listings?.length === 0 && (
          <EmptyState
            title="Bu kategoriyada hali e'lon yo'q"
            description={
              kind === "SERVICE"
                ? "Tez orada bu yo'nalishda xizmat ko'rsatuvchilar ro'yxatdan o'tadi."
                : "Tez orada shu kategoriyaga tegishli yangi e'lonlar paydo bo'ladi."
            }
          />
        )}

        {!isLoading && listings != null && listings.length > 0 && (
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {listings.map((listing) =>
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
      </div>
    </AppShell>
  );
}

function CategoryPage() {
  const { category, kind } = Route.useLoaderData();
  if (kind === "PROPERTY") return <PropertyDirectionView category={category} />;
  return <CatalogDirectionView category={category} kind={kind} />;
}
