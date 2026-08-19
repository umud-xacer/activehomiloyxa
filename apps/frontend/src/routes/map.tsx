import { createFileRoute, Link } from "@tanstack/react-router";
import { useSuspenseQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { MapPinned, Loader2 } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { YandexMapView, type AreaSearch, type MapMarker } from "@/components/map/YandexMapView";
import { propertyListOptions } from "@/features/properties/queries";
import type { Property, PropertyKind } from "@/features/properties/types";
import { formatPriceWithUnit } from "@/lib/format";
import { formatUzs } from "@/lib/catalog-client";
import { apiClient } from "@/lib/api-client";
import type { GeocodeResult } from "@/lib/geocoding";
import { MAP_CATEGORIES, categorizeByPath } from "@/features/map/demo-data";

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
    href: `/properties/${p.id}`,
    category,
    accent: MAP_CATEGORIES.find((c) => c.key === category)?.accent,
  };
}

const NEARBY_RADIUS_KM = 30;

/** "Search this place" -- a single real cross-category geo-radius query (`/search`'s `lat`/`lng`/
 * `radiusKm`, `apiClient.catalog.search`) around the geocoded point, covering every catalog
 * category at once (not just real estate). Replaces the previous client-side hack that fanned out
 * to three hardcoded, partly-stale category paths and filtered by distance itself. */
async function fetchNearbyListings(result: GeocodeResult): Promise<MapMarker[]> {
  const page = await apiClient.catalog
    .search({ lat: result.lat, lng: result.lng, radiusKm: NEARBY_RADIUS_KM, limit: 100 })
    .catch(() => ({ items: [] }));
  return page.items
    .filter((item) => item.location != null)
    .map((item) => {
      const category = categorizeByPath(item.categoryPath);
      return {
        id: item.id,
        lat: item.location!.latitude,
        lng: item.location!.longitude,
        label: formatUzs(item.price?.amount) || item.title,
        title: item.title,
        image: item.thumbnailUrl,
        href: `/listing/${item.id}`,
        category,
        accent: MAP_CATEGORIES.find((c) => c.key === category)?.accent,
      } satisfies MapMarker;
    });
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

  // Below `lg` (1024px) the sidebar list and map can't sit side-by-side, so without a toggle a
  // mobile/tablet visitor would have to scroll past up to 40 listing cards before ever reaching
  // the map -- the exact gap this route exists to avoid. Airbnb/Booking-style segmented switch
  // keeps both one tap away. Defaults to "map" since that's this route's whole purpose.
  const [mobileView, setMobileView] = useState<"list" | "map">("map");
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
    for (const m of propertyMarkers) byId.set(m.id, m);
    for (const m of areaMarkers) byId.set(m.id, m);
    return Array.from(byId.values());
  }, [propertyMarkers, areaMarkers]);

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
      <div className="pt-20 lg:grid lg:min-h-screen lg:grid-cols-[420px_1fr]">
        {/* Mobile/tablet-only: list<->map segmented toggle, sticky above whichever panel is
            showing. Hidden at `lg`+ where both panels sit side-by-side and no toggle is needed. */}
        <div className="sticky top-20 z-20 flex items-center justify-between gap-3 border-b border-border bg-background/95 px-4 py-3 backdrop-blur lg:hidden">
          <div className="min-w-0">
            <div className="font-display truncate text-sm font-semibold text-foreground">
              {markers.length.toLocaleString()} {t("mapPage.listings", "e'lon")}
            </div>
            {polygonIds && (
              <button
                onClick={() => setPolygonIds(null)}
                className="mt-0.5 text-[11px] font-medium text-primary"
              >
                {t("mapPage.clearArea", "Hududni tozalash")}
              </button>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-1 rounded-full border border-border bg-card p-1">
            <button
              type="button"
              onClick={() => setMobileView("list")}
              aria-pressed={mobileView === "list"}
              className={`rounded-full px-3.5 py-1.5 text-xs font-semibold transition ${
                mobileView === "list"
                  ? "bg-primary text-primary-foreground shadow-soft"
                  : "text-muted-foreground"
              }`}
            >
              {t("mapPage.listView", "Ro'yxat")}
            </button>
            <button
              type="button"
              onClick={() => setMobileView("map")}
              aria-pressed={mobileView === "map"}
              className={`rounded-full px-3.5 py-1.5 text-xs font-semibold transition ${
                mobileView === "map"
                  ? "bg-primary text-primary-foreground shadow-soft"
                  : "text-muted-foreground"
              }`}
            >
              {t("mapPage.mapView", "Xarita")}
            </button>
          </div>
        </div>

        {/* Sidebar list */}
        <aside
          className={`border-r border-border bg-background ${
            mobileView === "map" ? "hidden lg:block" : ""
          }`}
        >
          <div className="sticky top-20 hidden border-b border-border bg-background/95 px-6 py-5 backdrop-blur lg:block">
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

          <div className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2 lg:grid-cols-1 lg:p-6">
            {markers.slice(0, 40).map((m) => (
              <ListingRow
                key={m.id}
                marker={m}
                selected={selectedId === m.id}
                onFocus={() => {
                  focusOn(m);
                  setMobileView("map");
                }}
              />
            ))}
          </div>
        </aside>

        {/* Map column */}
        <div className={`relative ${mobileView === "list" ? "hidden lg:block" : ""}`}>
          {/* Explicit height here (rather than on YandexMapView's own `height` prop) so it can
              vary responsively: mobile/tablet lose extra vertical space to the sticky toggle bar
              above, `lg`+ doesn't have that bar at all. */}
          <div className="h-[calc(100dvh-10.5rem)] p-4 lg:sticky lg:top-20 lg:h-[calc(100vh-7rem)]">
            <YandexMapView
              markers={markers}
              center={{ lat: 41.3111, lng: 69.2797 }}
              zoom={6}
              focus={focus}
              height="100%"
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
