/**
 * MapView — Mapbox GL when VITE_MAPBOX_TOKEN is set, otherwise a premium
 * stylised fallback that matches the existing landing aesthetic so the
 * preview never looks broken.
 */
import { useEffect, useRef, useState } from "react";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import { Layers, Navigation, MapPin } from "lucide-react";
import { formatPriceWithUnit } from "@/lib/format";
import type { Property } from "@/features/properties/types";

const TOKEN = (import.meta.env.VITE_MAPBOX_TOKEN as string | undefined) ?? "";

const STYLES = {
  streets: "mapbox://styles/mapbox/streets-v12",
  satellite: "mapbox://styles/mapbox/satellite-streets-v12",
  dark: "mapbox://styles/mapbox/dark-v11",
  outdoors: "mapbox://styles/mapbox/outdoors-v12",
};

type StyleKey = keyof typeof STYLES;

interface Props {
  properties: Property[];
  center?: [number, number];
  zoom?: number;
  height?: string;
  onSelect?: (p: Property) => void;
}

export function MapView({
  properties,
  center = [55.2708, 25.2048],
  zoom = 3,
  height = "70vh",
  onSelect,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const markersRef = useRef<mapboxgl.Marker[]>([]);
  const [style, setStyle] = useState<StyleKey>("streets");

  // Initialise Mapbox once
  useEffect(() => {
    if (!TOKEN || !containerRef.current || mapRef.current) return;
    mapboxgl.accessToken = TOKEN;
    const map = new mapboxgl.Map({
      container: containerRef.current,
      style: STYLES[style],
      center,
      zoom,
      attributionControl: false,
    });
    map.addControl(new mapboxgl.NavigationControl({ visualizePitch: true }), "top-right");
    map.addControl(
      new mapboxgl.GeolocateControl({
        positionOptions: { enableHighAccuracy: true },
        trackUserLocation: true,
      }),
      "top-right",
    );
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Style switching
  useEffect(() => {
    if (!mapRef.current) return;
    mapRef.current.setStyle(STYLES[style]);
  }, [style]);

  // Markers
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];

    properties.forEach((p) => {
      const el = document.createElement("button");
      el.type = "button";
      el.className =
        "inline-flex items-center gap-1 rounded-full bg-white px-2.5 py-1 text-xs font-semibold text-foreground shadow-elevated hover:bg-primary hover:text-primary-foreground transition";
      el.innerText = formatPriceWithUnit(p.price, p.currency, p.listing_type);
      el.addEventListener("click", () => onSelect?.(p));
      const marker = new mapboxgl.Marker({ element: el })
        .setLngLat([p.location.lng, p.location.lat])
        .addTo(map);
      markersRef.current.push(marker);
    });
  }, [properties, onSelect]);

  if (!TOKEN) {
    return <FallbackMap properties={properties} height={height} onSelect={onSelect} />;
  }

  return (
    <div className="relative overflow-hidden rounded-3xl border border-border shadow-elevated" style={{ height }}>
      <div ref={containerRef} className="absolute inset-0" />
      <div className="absolute left-4 top-4 flex flex-col gap-1 rounded-2xl border border-border bg-card/90 p-1 shadow-soft backdrop-blur">
        {(Object.keys(STYLES) as StyleKey[]).map((k) => (
          <button
            key={k}
            onClick={() => setStyle(k)}
            className={`rounded-xl px-3 py-1.5 text-xs font-medium capitalize transition ${
              style === k
                ? "bg-primary text-primary-foreground"
                : "text-foreground/70 hover:bg-muted"
            }`}
          >
            {k}
          </button>
        ))}
      </div>
    </div>
  );
}

function FallbackMap({
  properties,
  height,
  onSelect,
}: {
  properties: Property[];
  height: string;
  onSelect?: (p: Property) => void;
}) {
  // Project lat/lng into a 0..100 box, just for visualisation in the preview.
  const lats = properties.map((p) => p.location.lat);
  const lngs = properties.map((p) => p.location.lng);
  const minLat = Math.min(...lats, -10);
  const maxLat = Math.max(...lats, 50);
  const minLng = Math.min(...lngs, -10);
  const maxLng = Math.max(...lngs, 60);
  return (
    <div
      className="relative overflow-hidden rounded-3xl border border-border bg-card shadow-elevated"
      style={{ height }}
    >
      <div
        className="absolute inset-0"
        style={{
          background:
            "radial-gradient(circle at 30% 40%, oklch(0.62 0.19 275 / 0.25), transparent 50%), radial-gradient(circle at 70% 60%, oklch(0.72 0.16 200 / 0.25), transparent 50%), linear-gradient(135deg, oklch(0.18 0.04 265), oklch(0.24 0.06 270))",
        }}
      />
      <div
        className="absolute inset-0 opacity-20 [background-image:linear-gradient(to_right,white_1px,transparent_1px),linear-gradient(to_bottom,white_1px,transparent_1px)] [background-size:80px_80px]"
        aria-hidden
      />
      {properties.slice(0, 80).map((p) => {
        const x = ((p.location.lng - minLng) / (maxLng - minLng)) * 100;
        const y = 100 - ((p.location.lat - minLat) / (maxLat - minLat)) * 100;
        return (
          <button
            key={p.id}
            onClick={() => onSelect?.(p)}
            className="absolute -translate-x-1/2 -translate-y-full"
            style={{ left: `${x}%`, top: `${y}%` }}
          >
            <span className="inline-flex items-center gap-1 rounded-full bg-white px-2 py-0.5 text-[11px] font-semibold text-foreground shadow-elevated">
              <MapPin className="size-3 text-primary" />
              {formatPriceWithUnit(p.price, p.currency, p.listing_type)}
            </span>
          </button>
        );
      })}
      <div className="absolute left-4 top-4 flex flex-col gap-2">
        <button className="glass flex size-10 items-center justify-center rounded-xl text-foreground shadow-soft">
          <Layers className="size-4" />
        </button>
        <button className="glass flex size-10 items-center justify-center rounded-xl text-foreground shadow-soft">
          <Navigation className="size-4" />
        </button>
      </div>
      <div className="glass absolute bottom-4 left-4 rounded-2xl px-3 py-2 text-[11px] text-foreground/80 shadow-soft">
        Demo map active · add <code className="rounded bg-card/60 px-1">VITE_MAPBOX_TOKEN</code> for live Mapbox
      </div>
    </div>
  );
}
