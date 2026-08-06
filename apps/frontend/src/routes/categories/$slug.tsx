import { useMemo } from "react";
import { createFileRoute, notFound, useNavigate } from "@tanstack/react-router";
import { zodValidator, fallback } from "@tanstack/zod-adapter";
import { useSuspenseQuery, useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { motion } from "framer-motion";
import { Map as MapIcon, Tag, Layers } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { PropertyCard } from "@/components/data/PropertyCard";
import { PropertyGridSkeleton } from "@/components/data/PropertyCardSkeleton";
import { EmptyState } from "@/components/state/EmptyState";
import { ErrorState } from "@/components/state/ErrorState";
import { LeafletMapView, type MapMarker } from "@/components/map/LeafletMapView";
import { propertyListOptions } from "@/features/properties/queries";
import type { Property, PropertyQuery } from "@/features/properties/types";
import { catalogClient } from "@/lib/catalog-client";
import { categoryLabel } from "@/components/site/CategoryCarousel";
import { formatPriceWithUnit } from "@/lib/format";
import { Link } from "@tanstack/react-router";

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

    const query: PropertyQuery = {
      category_id: category.id,
      sort: deps.sort,
      page: deps.page,
      page_size: 24,
    };
    await context.queryClient.ensureQueryData(propertyListOptions(query));
    return { category };
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

function CategoryPage() {
  const { category } = Route.useLoaderData();
  const search = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });

  const query: PropertyQuery = {
    category_id: category.id,
    sort: search.sort,
    page: search.page,
    page_size: 24,
  };
  const { data } = useSuspenseQuery(propertyListOptions(query));

  const { data: allCategories = [] } = useQuery({
    queryKey: ["catalog", "categories", "all"],
    queryFn: () => catalogClient.listCategories(),
  });
  const children = allCategories.filter((c) => c.status === "ACTIVE" && c.parentId === category.id);
  const parent = category.parentId
    ? allCategories.find((c) => c.id === category.parentId)
    : undefined;
  const categoryHref = (path: string): string => `/categories/${path.replace(/^\//, "")}`;

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

      {children.length > 0 && (
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
      )}

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
