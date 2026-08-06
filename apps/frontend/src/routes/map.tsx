import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery, useSuspenseQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { MapPinned, Loader2 } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { LeafletMapView, type AreaSearch, type MapMarker } from "@/components/map/LeafletMapView";
import { propertyListOptions } from "@/features/properties/queries";
import type { Property, PropertyKind } from "@/features/properties/types";
import { formatPriceWithUnit } from "@/lib/format";
import { catalogClient, formatUzs } from "@/lib/catalog-client";
import { distanceMeters } from "@/lib/routing";
import type { GeocodeResult } from "@/lib/geocoding";
import { getDemoMapMarkers, MAP_CATEGORIES } from "@/features/map/demo-data";

const KIND_TO_CATEGORY: Record<PropertyKind, string> = {
  apartment: "apartment",
  building: "commercial",
  house: "house",
  cottage: "house",
  country: "house",
  commercial: "commercial",
  land: "commercial",
  hotel: "commercial",
  hostel: "commercial",
};

function toMarker(p: Property): MapMarker {
  const category = KIND_TO_CATEGORY[p.kind];
  return {
    id: p.id,
    lat: p.location.lat,
    lng: p.location.lng,
    label: formatPriceWithUnit(p.price, p.currency, p.listing_type),
    title: p.title,
    subtitle: `${p.city}, ${p.country}`,
    image: p.media[0]?.url,
    href: `/properties/${p.slug}`,
    category,
    accent: MAP_CATEGORIES.find((c) => c.key === category)?.accent,
  };
}

/** Every catalog category with real coordinates -- combined so a location search surfaces
 * everything nearby (homes, materials, recreation venues), not just real-estate listings.
 * There's no separate "company"/"service" catalog category yet (see homepage's Organizations
 * section for those, which is curated content rather than live listings). */
const NEARBY_CATEGORY_PATHS: { path: string; category: string }[] = [
  { path: "/dam-olish-maskanlari", category: "recreation" },
  { path: "/qurilish-mollari", category: "materials" },
  { path: "/kvartira", category: "apartment" },
];
const NEARBY_RADIUS_METERS = 30_000;

async function fetchNearbyListings(result: GeocodeResult): Promise<MapMarker[]> {
  const lists = await Promise.all(
    NEARBY_CATEGORY_PATHS.map(async ({ path, category }) => {
      const items = await catalogClient.listingsByCategoryPath(path, 80).catch(() => []);
      return items.map((listing) => ({ listing, category }));
    }),
  );
  const seen = new Map<string, MapMarker>();
  for (const { listing, category } of lists.flat()) {
    if (!listing.location) continue;
    const point = { lat: listing.location.latitude, lng: listing.location.longitude };
    if (distanceMeters({ lat: result.lat, lng: result.lng }, point) > NEARBY_RADIUS_METERS)
      continue;
    seen.set(listing.id, {
      id: listing.id,
      lat: point.lat,
      lng: point.lng,
      label: formatUzs(listing.price?.amount),
      title: listing.title,
      subtitle: listing.attributes.address ? String(listing.attributes.address) : undefined,
      href: `/properties/${listing.id}`,
      category,
      accent: MAP_CATEGORIES.find((c) => c.key === category)?.accent,
    });
  }
  return Array.from(seen.values());
}

export const Route = createFileRoute("/map")({
  head: () => ({
    meta: [
      { title: "Map search — ActiveHome" },
      {
        name: "description",
        content:
          "Real-time interactive map search. Satellite, terrain and radius/polygon search across every category -- homes, materials, recreation venues and companies.",
      },
    ],
  }),
  loader: ({ context }) =>
    context.queryClient.ensureQueryData(propertyListOptions({ page_size: 120 })),
  component: MapPage,
});

function ListingRow({
  marker,
  selected,
  onFocus,
}: {
  marker: MapMarker;
  selected: boolean;
  onFocus: () => void;
}) {
  const categoryLabel = MAP_CATEGORIES.find((c) => c.key === marker.category)?.label;
  return (
    <div
      className={`group relative overflow-hidden rounded-2xl border bg-card shadow-soft transition hover:-translate-y-0.5 hover:shadow-elevated ${
        selected ? "border-primary ring-1 ring-primary" : "border-border"
      }`}
    >
      <button
        type="button"
        onClick={onFocus}
        aria-label="Xaritada ko'rish"
        title="Xaritada ko'rish"
        className="absolute right-3 top-3 z-10 flex size-8 items-center justify-center rounded-full border border-border bg-card/90 text-foreground/70 shadow-soft backdrop-blur transition hover:border-primary/40 hover:text-primary"
      >
        <MapPinned className="size-3.5" />
      </button>
      <Link to={marker.href || "/map"} className="block p-4 pr-14">
        {categoryLabel && (
          <div className="flex items-center gap-1.5">
            <span
              className="size-1.5 rounded-full"
              style={{ background: marker.accent || "var(--primary)" }}
            />
            <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              {categoryLabel}
            </span>
          </div>
        )}
        <div className="font-display mt-1 text-sm font-semibold leading-tight text-foreground">
          {marker.title}
        </div>
        {marker.subtitle && (
          <div className="mt-1 text-xs text-muted-foreground">{marker.subtitle}</div>
        )}
        <div className="mt-2 text-sm font-semibold text-primary">{marker.label}</div>
      </Link>
    </div>
  );
}

function MapPage() {
  const { t } = useTranslation();
  const { data } = useSuspenseQuery(propertyListOptions({ page_size: 120 }));
  const { data: demoMarkers = [] } = useQuery({
    queryKey: ["map", "demo-markers"],
    queryFn: getDemoMapMarkers,
    staleTime: Infinity,
  });

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [focus, setFocus] = useState<{
    id: string;
    lat: number;
    lng: number;
    zoom?: number;
  } | null>(null);
  const [polygonIds, setPolygonIds] = useState<Set<string> | null>(null);
  const [activeCategories, setActiveCategories] = useState<string[]>([]);
  const [areaMarkers, setAreaMarkers] = useState<MapMarker[]>([]);
  const [areaLabel, setAreaLabel] = useState<string | null>(null);
  const [areaLoading, setAreaLoading] = useState(false);

  const propertyMarkers = useMemo(() => data.items.map(toMarker), [data.items]);

  const allMarkers = useMemo(() => {
    const byId = new Map<string, MapMarker>();
    for (const m of demoMarkers) byId.set(m.id, m);
    for (const m of propertyMarkers) byId.set(m.id, m);
    for (const m of areaMarkers) byId.set(m.id, m);
    return Array.from(byId.values());
  }, [demoMarkers, propertyMarkers, areaMarkers]);

  const markers = useMemo(() => {
    return allMarkers.filter((m) => {
      if (polygonIds && !polygonIds.has(m.id)) return false;
      if (activeCategories.length > 0 && (!m.category || !activeCategories.includes(m.category)))
        return false;
      return true;
    });
  }, [allMarkers, polygonIds, activeCategories]);

  const onPlaceSearch = async (result: GeocodeResult) => {
    setAreaLabel(result.label);
    setAreaLoading(true);
    try {
      setAreaMarkers(await fetchNearbyListings(result));
    } finally {
      setAreaLoading(false);
    }
  };

  const focusOn = (m: MapMarker) => {
    setSelectedId(m.id);
    setFocus({ id: m.id, lat: m.lat, lng: m.lng, zoom: 14 });
  };

  const onAreaSearch = (area: AreaSearch) => {
    const inside = allMarkers.filter(
      (m) =>
        m.lng >= area.bbox.west &&
        m.lng <= area.bbox.east &&
        m.lat >= area.bbox.south &&
        m.lat <= area.bbox.north,
    );
    setPolygonIds(new Set(inside.map((m) => m.id)));
  };

  return (
    <AppShell>
      <div className="grid min-h-screen pt-20 lg:grid-cols-[420px_1fr]">
        {/* Sidebar list */}
        <aside className="border-r border-border bg-background">
          <div className="sticky top-20 border-b border-border bg-background/95 px-6 py-5 backdrop-blur">
            <div className="text-xs uppercase tracking-widest text-muted-foreground">
              {t("mapPage.eyebrow", "Xarita bo'yicha qidiruv")}
            </div>
            <h1 className="font-display mt-1 text-2xl font-semibold text-foreground">
              {markers.length.toLocaleString()} {t("mapPage.listings", "e'lon")}
              {polygonIds && (
                <button
                  onClick={() => setPolygonIds(null)}
                  className="ml-3 rounded-full border border-border bg-card px-2.5 py-0.5 align-middle text-[11px] font-medium text-foreground/70 hover:bg-muted"
                >
                  {t("mapPage.clearArea", "Hududni tozalash")}
                </button>
              )}
            </h1>
            <p className="mt-1 text-xs text-muted-foreground">
              {areaLabel
                ? `"${areaLabel}" atrofida topilgan e'lonlar`
                : t(
                    "mapPage.hint",
                    "Ko'rinadigan e'lonlarni filtrlash uchun xaritadagi ko'pburchak yoki radius asbobidan foydalaning.",
                  )}
              {areaLoading && (
                <Loader2 className="ml-1.5 inline size-3 animate-spin align-[-2px]" />
              )}
            </p>
          </div>

          <div className="grid grid-cols-1 gap-4 p-6 sm:grid-cols-2 lg:grid-cols-1">
            {markers.slice(0, 40).map((m) => (
              <ListingRow
                key={m.id}
                marker={m}
                selected={selectedId === m.id}
                onFocus={() => focusOn(m)}
              />
            ))}
          </div>
        </aside>

        {/* Map column */}
        <div className="relative">
          <div className="sticky top-20 p-4">
            <LeafletMapView
              markers={markers}
              center={{ lat: 41.3111, lng: 69.2797 }}
              zoom={6}
              focus={focus}
              height="calc(100vh - 7rem)"
              onSelect={(m) => setSelectedId(m.id)}
              onAreaSearch={onAreaSearch}
              onPlaceSearch={onPlaceSearch}
              filterOptions={MAP_CATEGORIES}
              activeFilterKeys={activeCategories}
              onFilterKeysChange={setActiveCategories}
            />
          </div>
        </div>
      </div>
    </AppShell>
  );
}
