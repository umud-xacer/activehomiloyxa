/* eslint-disable @typescript-eslint/no-explicit-any */
/**
 * Yandex Maps surface for ActiveHome — a real interactive map (NOT a placeholder), tuned for
 * Uzbekistan/CIS where Yandex out-covers Google/Mapbox.
 *
 * Drop-in replacement for `GoogleMapView`: identical `Props`/`AreaSearch` contract, so parents
 * (`/map`, property detail) need only swap the import. Features:
 *  - Price-pill markers (`islands#...StretchyIcon` preset carries the price as its caption)
 *  - Marker clustering at low zoom (`ymaps.Clusterer`)
 *  - Layer switcher: Street / Satellite / Hybrid
 *  - User geolocation
 *  - "Search this area" -> emits the current viewport bbox via `onAreaSearch` (parent refetches)
 *  - Click marker -> balloon + `onSelect`
 *
 * Coordinates: Yandex uses [lat, lng] order (latitude first) -- the opposite of GeoJSON/Mapbox --
 * so every conversion below is deliberate.
 */
import { useEffect, useRef, useState } from "react";
import { Layers, Navigation, Search, AlertTriangle } from "lucide-react";
import { loadYandexMaps } from "@/lib/yandex-maps";
import { formatPriceWithUnit } from "@/lib/format";
import type { Property } from "@/features/properties/types";

interface BoundsBox {
  west: number;
  south: number;
  east: number;
  north: number;
}

export interface AreaSearch {
  bbox: BoundsBox;
  kind: "polygon" | "circle";
  center?: { lat: number; lng: number };
  radiusMeters?: number;
}

interface Props {
  properties: Property[];
  center?: { lat: number; lng: number };
  zoom?: number;
  height?: string;
  className?: string;
  onSelect?: (p: Property) => void;
  onAreaSearch?: (area: AreaSearch) => void;
  showCountBadge?: boolean;
}

type StyleKey = "yandex#map" | "yandex#satellite" | "yandex#hybrid";

const STYLE_LABELS: Record<StyleKey, string> = {
  "yandex#map": "Ko'cha",
  "yandex#satellite": "Sputnik",
  "yandex#hybrid": "Gibrid",
};

export function YandexMapView({
  properties,
  center = { lat: 41.3111, lng: 69.2797 },
  zoom = 5,
  height = "70vh",
  className = "",
  onSelect,
  onAreaSearch,
  showCountBadge = true,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<any>(null);
  const clustererRef = useRef<any>(null);
  const ymapsRef = useRef<any>(null);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  const [style, setStyle] = useState<StyleKey>("yandex#map");
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);

  // Init once
  useEffect(() => {
    let cancelled = false;
    loadYandexMaps()
      .then((ymaps) => {
        if (cancelled || !containerRef.current) return;
        ymapsRef.current = ymaps;
        const map = new ymaps.Map(
          containerRef.current,
          { center: [center.lat, center.lng], zoom, type: style, controls: [] },
          { suppressMapOpenBlock: true },
        );
        const clusterer = new ymaps.Clusterer({
          preset: "islands#invertedBlueClusterIcons",
          groupByCoordinates: false,
          clusterDisableClickZoom: false,
          gridSize: 64,
        });
        map.geoObjects.add(clusterer);
        mapRef.current = map;
        clustererRef.current = clusterer;
        setReady(true);
      })
      .catch((err) => {
        console.error("[YandexMapView] failed to load", err);
        setFailed(true);
      });
    return () => {
      cancelled = true;
      mapRef.current?.destroy?.();
      mapRef.current = null;
      clustererRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Rebuild markers when properties change
  useEffect(() => {
    const ymaps = ymapsRef.current;
    const clusterer = clustererRef.current;
    if (!ready || !ymaps || !clusterer) return;
    clusterer.removeAll();
    const placemarks = properties
      .filter((p) => Number.isFinite(p.location.lat) && Number.isFinite(p.location.lng))
      .map((p) => {
        const label = formatPriceWithUnit(p.price, p.currency, p.listing_type);
        const pm = new ymaps.Placemark(
          [p.location.lat, p.location.lng],
          { iconCaption: label, hintContent: p.title },
          { preset: "islands#blueStretchyIcon", hasBalloon: false },
        );
        pm.events.add("click", () => onSelectRef.current?.(p));
        return pm;
      });
    clusterer.add(placemarks);
  }, [properties, ready]);

  // React to center/zoom prop changes (e.g. parent selects a listing)
  useEffect(() => {
    if (!ready || !mapRef.current) return;
    mapRef.current.setCenter([center.lat, center.lng], zoom, { duration: 350 });
  }, [center.lat, center.lng, zoom, ready]);

  // Layer switch
  useEffect(() => {
    if (!ready || !mapRef.current) return;
    mapRef.current.setType(style);
  }, [style, ready]);

  const goToMyLocation = () => {
    if (!navigator.geolocation || !mapRef.current) return;
    navigator.geolocation.getCurrentPosition((pos) => {
      mapRef.current?.setCenter([pos.coords.latitude, pos.coords.longitude], 13, { duration: 400 });
    });
  };

  const searchThisArea = () => {
    const map = mapRef.current;
    if (!map || !onAreaSearch) return;
    // Yandex getBounds() -> [[southLat, westLng], [northLat, eastLng]]
    const b = map.getBounds();
    if (!b) return;
    onAreaSearch({
      bbox: { south: b[0][0], west: b[0][1], north: b[1][0], east: b[1][1] },
      kind: "polygon",
    });
  };

  if (failed) {
    return (
      <div
        className={`relative flex flex-col items-center justify-center gap-3 rounded-3xl border border-dashed border-border bg-card/40 p-10 text-center ${className}`}
        style={{ height }}
      >
        <div className="flex size-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
          <AlertTriangle className="size-5" />
        </div>
        <div className="font-display text-lg font-semibold text-foreground">Xarita yuklanmadi</div>
        <p className="max-w-sm text-sm text-muted-foreground">
          Yandex Maps ulanmadi. Internetni tekshiring yoki <code className="rounded bg-card/60 px-1">VITE_YANDEX_MAPS_API_KEY</code> kalitini qo'shing.
        </p>
      </div>
    );
  }

  return (
    <div
      className={`relative overflow-hidden rounded-3xl border border-border bg-card shadow-elevated ${className}`}
      style={{ height }}
    >
      <div ref={containerRef} className="absolute inset-0" />

      {/* Layer switcher */}
      <div className="glass absolute left-4 top-4 flex flex-col gap-1 rounded-2xl p-1 shadow-soft">
        <div className="flex items-center gap-1 px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-foreground/60">
          <Layers className="size-3" /> Qatlam
        </div>
        {(Object.keys(STYLE_LABELS) as StyleKey[]).map((k) => (
          <button
            key={k}
            onClick={() => setStyle(k)}
            className={`rounded-xl px-3 py-1.5 text-xs font-medium transition ${
              style === k ? "bg-primary text-primary-foreground" : "text-foreground/70 hover:bg-muted"
            }`}
          >
            {STYLE_LABELS[k]}
          </button>
        ))}
      </div>

      {/* Right controls */}
      <div className="absolute right-4 top-4 flex flex-col gap-2">
        <button
          onClick={goToMyLocation}
          title="Mening joylashuvim"
          className="glass flex size-10 items-center justify-center rounded-xl text-foreground shadow-soft transition hover:text-primary"
        >
          <Navigation className="size-4" />
        </button>
        {onAreaSearch && (
          <button
            onClick={searchThisArea}
            className="glass inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-semibold text-foreground shadow-soft transition hover:text-primary"
          >
            <Search className="size-3.5" /> Shu hududda
          </button>
        )}
      </div>

      {showCountBadge && (
        <div className="glass absolute bottom-4 left-4 rounded-2xl px-3 py-2 text-[11px] font-medium text-foreground/80 shadow-soft">
          {properties.length.toLocaleString()} e'lon xaritada
        </div>
      )}

      {!ready && !failed && (
        <div className="absolute inset-0 flex items-center justify-center bg-card/60 backdrop-blur-sm">
          <div className="size-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        </div>
      )}
    </div>
  );
}
