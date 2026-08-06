/// <reference types="google.maps" />
/**
 * Premium Google Maps surface for ActiveHome.
 *
 * Real interactive map (NOT a placeholder). Features:
 *  - Map style switcher: Roadmap / Satellite / Hybrid / Terrain
 *  - Traffic layer toggle
 *  - User geolocation
 *  - Drawing tools: polygon + radius (circle), with Clear control
 *  - Premium price-pill markers (SVG)
 *  - Marker clustering at zoom
 *  - InfoWindow on marker click + onSelect callback
 *  - Street View toggle
 *
 * Backend-ready: every interaction emits typed callbacks
 * (`onSelect`, `onAreaSearch`) so the parent can refetch from the API.
 *
 * If the Google connector ever goes missing, the component renders a
 * branded "configure maps" panel instead of breaking the layout.
 */
import { useEffect, useId, useMemo, useRef, useState } from "react";
import * as MarkerClustererNS from "@googlemaps/markerclusterer";
type MarkerClustererType = InstanceType<typeof import("@googlemaps/markerclusterer").MarkerClusterer>;
const MarkerClusterer =
  (MarkerClustererNS as unknown as { MarkerClusterer?: typeof import("@googlemaps/markerclusterer").MarkerClusterer }).MarkerClusterer ??
  ((MarkerClustererNS as unknown as { default: { MarkerClusterer: typeof import("@googlemaps/markerclusterer").MarkerClusterer } }).default?.MarkerClusterer);
import {
  Layers,
  Navigation,
  PenTool,
  Circle as CircleIcon,
  Eye,
  Trash2,
  CarFront,
  AlertTriangle,
} from "lucide-react";
import { hasGoogleMapsKey, loadGoogleMaps } from "@/lib/google-maps";
import { formatPriceWithUnit } from "@/lib/format";
import type { Property } from "@/features/properties/types";

type StyleKey = "roadmap" | "satellite" | "hybrid" | "terrain";

/** Local shim — google.maps.drawing types in v3.65+ are slimmed down. */
interface DrawingMgrShim {
  setMap(map: google.maps.Map | null): void;
  setDrawingMode(mode: string | null): void;
}
type OverlayCompleteEvent = { type: string; overlay: google.maps.MVCObject & { setMap?: (m: google.maps.Map | null) => void } };

interface BoundsBox {
  west: number;
  south: number;
  east: number;
  north: number;
}

export interface AreaSearch {
  /** Bounding box of the drawn shape, ready to send to the API as ?bbox= */
  bbox: BoundsBox;
  /** "polygon" or "circle" */
  kind: "polygon" | "circle";
  /** Circle only: center + radius (meters) */
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
  /** Fires when the user finishes drawing a polygon or radius */
  onAreaSearch?: (area: AreaSearch) => void;
  /** Show the bottom-left "N listings" pill */
  showCountBadge?: boolean;
}

const STYLE_LABELS: Record<StyleKey, string> = {
  roadmap: "Street",
  satellite: "Satellite",
  hybrid: "Hybrid",
  terrain: "Terrain",
};

function pricePillSvg(label: string, selected = false): string {
  const fill = selected ? "#2D3270" : "#FFFFFF";
  const stroke = selected ? "#FFFFFF" : "#2D3270";
  const text = selected ? "#FFFFFF" : "#1B1F4A";
  const w = Math.max(56, label.length * 8 + 18);
  return `
    <svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="34" viewBox="0 0 ${w} 34">
      <defs>
        <filter id="s" x="-20%" y="-20%" width="140%" height="160%">
          <feDropShadow dx="0" dy="2" stdDeviation="2" flood-opacity="0.18"/>
        </filter>
      </defs>
      <g filter="url(#s)">
        <rect x="1" y="1" rx="14" ry="14" width="${w - 2}" height="26" fill="${fill}" stroke="${stroke}" stroke-width="1.2"/>
        <text x="${w / 2}" y="18" text-anchor="middle" font-family="Inter, system-ui" font-size="11.5" font-weight="700" fill="${text}">${label}</text>
        <path d="M${w / 2 - 5} 27 L${w / 2} 33 L${w / 2 + 5} 27 Z" fill="${fill}" stroke="${stroke}" stroke-width="1.2"/>
      </g>
    </svg>`;
}

function pricePillIcon(google: typeof globalThis.google, label: string, selected = false): google.maps.Icon {
  const w = Math.max(56, label.length * 8 + 18);
  return {
    url: `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(pricePillSvg(label, selected))}`,
    scaledSize: new google.maps.Size(w, 34),
    anchor: new google.maps.Point(w / 2, 33),
  };
}

export function GoogleMapView({
  properties,
  center = { lat: 25.2048, lng: 55.2708 },
  zoom = 3,
  height = "70vh",
  className = "",
  onSelect,
  onAreaSearch,
  showCountBadge = true,
}: Props) {
  const containerId = useId();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<google.maps.Map | null>(null);
  const clustererRef = useRef<MarkerClustererType | null>(null);
  const markersRef = useRef<google.maps.Marker[]>([]);
  const trafficRef = useRef<google.maps.TrafficLayer | null>(null);
  const drawingMgrRef = useRef<(google.maps.drawing.DrawingManager & DrawingMgrShim) | null>(null);
  const overlaysRef = useRef<Array<google.maps.MVCObject & { setMap?: (m: google.maps.Map | null) => void }>>([]);
  const infoRef = useRef<google.maps.InfoWindow | null>(null);

  const [style, setStyle] = useState<StyleKey>("roadmap");
  const [traffic, setTraffic] = useState(false);
  const [drawMode, setDrawMode] = useState<"none" | "polygon" | "circle">("none");
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);

  // Initialise map once
  useEffect(() => {
    if (!hasGoogleMapsKey() || !containerRef.current) {
      setFailed(!hasGoogleMapsKey());
      return;
    }
    let cancelled = false;
    loadGoogleMaps()
      .then((google) => {
        if (cancelled || !containerRef.current) return;
        const map = new google.maps.Map(containerRef.current, {
          center,
          zoom,
          mapTypeId: style,
          disableDefaultUI: true,
          zoomControl: true,
          gestureHandling: "greedy",
          clickableIcons: false,
          backgroundColor: "transparent",
        });
        mapRef.current = map;
        infoRef.current = new google.maps.InfoWindow({ disableAutoPan: false });
        setReady(true);
      })
      .catch((err) => {
        console.error("[GoogleMapView] failed to load", err);
        setFailed(true);
      });
    return () => {
      cancelled = true;
      clustererRef.current?.clearMarkers();
      markersRef.current.forEach((m) => m.setMap(null));
      markersRef.current = [];
      overlaysRef.current.forEach((o) => o.setMap?.(null));
      overlaysRef.current = [];
      drawingMgrRef.current?.setMap(null);
      trafficRef.current?.setMap(null);
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Style switching
  useEffect(() => {
    mapRef.current?.setMapTypeId(style);
  }, [style]);

  // Traffic toggle
  useEffect(() => {
    if (!ready || !mapRef.current) return;
    const google = globalThis.google;
    if (traffic) {
      trafficRef.current ??= new google.maps.TrafficLayer();
      trafficRef.current.setMap(mapRef.current);
    } else {
      trafficRef.current?.setMap(null);
    }
  }, [traffic, ready]);

  // Markers + clustering
  useEffect(() => {
    if (!ready || !mapRef.current) return;
    const google = globalThis.google;
    const map = mapRef.current;

    clustererRef.current?.clearMarkers();
    markersRef.current.forEach((m) => m.setMap(null));
    markersRef.current = [];

    const markers = properties.map((p) => {
      const label = formatPriceWithUnit(p.price, p.currency, p.listing_type);
      const marker = new google.maps.Marker({
        position: { lat: p.location.lat, lng: p.location.lng },
        icon: pricePillIcon(google, label),
        title: p.title,
      });
      marker.addListener("click", () => {
        markersRef.current.forEach((m, idx) => {
          const prop = properties[idx];
          if (!prop) return;
          const lbl = formatPriceWithUnit(prop.price, prop.currency, prop.listing_type);
          m.setIcon(pricePillIcon(google, lbl, m === marker));
        });
        infoRef.current?.setContent(infoWindowHtml(p));
        infoRef.current?.open({ anchor: marker, map });
        onSelect?.(p);
      });
      return marker;
    });
    markersRef.current = markers;

    clustererRef.current = new MarkerClusterer({ map, markers });
  }, [properties, ready, onSelect]);

  // Drawing mode
  useEffect(() => {
    if (!ready || !mapRef.current) return;
    const google = globalThis.google;
    const map = mapRef.current;

    drawingMgrRef.current?.setMap(null);
    drawingMgrRef.current = null;
    if (drawMode === "none") return;

    const DrawCtor = google.maps.drawing.DrawingManager as unknown as new (
      opts: Record<string, unknown>,
    ) => google.maps.drawing.DrawingManager & DrawingMgrShim;
    const mgr = new DrawCtor({
      drawingMode:
        drawMode === "polygon"
          ? google.maps.drawing.OverlayType.POLYGON
          : google.maps.drawing.OverlayType.CIRCLE,
      drawingControl: false,
      polygonOptions: {
        fillColor: "#2D3270",
        fillOpacity: 0.15,
        strokeColor: "#2D3270",
        strokeWeight: 2,
        editable: true,
        clickable: false,
      },
      circleOptions: {
        fillColor: "#2D3270",
        fillOpacity: 0.12,
        strokeColor: "#2D3270",
        strokeWeight: 2,
        editable: true,
        clickable: false,
      },
    });
    mgr.setMap(map);
    drawingMgrRef.current = mgr;

    const listener = google.maps.event.addListener(
      mgr,
      "overlaycomplete",
      (e: OverlayCompleteEvent) => {
        overlaysRef.current.push(e.overlay as never);
        mgr.setDrawingMode(null);
        setDrawMode("none");

        if (e.type === google.maps.drawing.OverlayType.POLYGON) {
          const poly = e.overlay as unknown as google.maps.Polygon;
          const bounds = new google.maps.LatLngBounds();
          poly.getPath().forEach((latLng: google.maps.LatLng) => bounds.extend(latLng));
          onAreaSearch?.({
            kind: "polygon",
            bbox: bboxFromBounds(bounds),
          });
        } else if (e.type === google.maps.drawing.OverlayType.CIRCLE) {
          const circle = e.overlay as unknown as google.maps.Circle;
          const bounds = circle.getBounds();
          if (!bounds) return;
          const c = circle.getCenter();
          onAreaSearch?.({
            kind: "circle",
            bbox: bboxFromBounds(bounds),
            center: c ? { lat: c.lat(), lng: c.lng() } : undefined,
            radiusMeters: circle.getRadius(),
          });
        }
      },
    );

    return () => google.maps.event.removeListener(listener);
  }, [drawMode, ready, onAreaSearch]);

  const clearOverlays = () => {
    overlaysRef.current.forEach((o) => o.setMap?.(null));
    overlaysRef.current = [];
  };

  const geolocate = () => {
    if (!navigator.geolocation || !mapRef.current) return;
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const latLng = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        mapRef.current?.panTo(latLng);
        mapRef.current?.setZoom(13);
      },
      (err) => console.warn("[geolocation]", err.message),
      { enableHighAccuracy: true, timeout: 8000 },
    );
  };

  const openStreetView = () => {
    if (!mapRef.current) return;
    const sv = mapRef.current.getStreetView();
    sv.setPosition(mapRef.current.getCenter()!);
    sv.setVisible(true);
  };

  const containerStyle = useMemo(() => ({ height }), [height]);

  if (failed) {
    return (
      <div
        className={`relative flex flex-col items-center justify-center gap-3 rounded-3xl border border-dashed border-border bg-card/40 p-10 text-center ${className}`}
        style={containerStyle}
      >
        <div className="flex size-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
          <AlertTriangle className="size-5" />
        </div>
        <div className="font-display text-lg font-semibold text-foreground">Maps connector unavailable</div>
        <p className="max-w-sm text-sm text-muted-foreground">
          The Google Maps connection is not active for this preview. Reconnect Google Maps Platform to enable live maps.
        </p>
      </div>
    );
  }

  return (
    <div
      className={`relative overflow-hidden rounded-3xl border border-border bg-card shadow-elevated ${className}`}
      style={containerStyle}
    >
      <div id={containerId} ref={containerRef} className="absolute inset-0" />

      {/* Style switcher */}
      <div className="glass absolute left-4 top-4 flex flex-col gap-1 rounded-2xl p-1 shadow-soft">
        <div className="flex items-center gap-1 px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-foreground/60">
          <Layers className="size-3" /> Layers
        </div>
        {(Object.keys(STYLE_LABELS) as StyleKey[]).map((k) => (
          <button
            key={k}
            onClick={() => setStyle(k)}
            className={`rounded-xl px-3 py-1.5 text-left text-xs font-medium transition ${
              style === k
                ? "bg-primary text-primary-foreground shadow-soft"
                : "text-foreground/80 hover:bg-card/60"
            }`}
          >
            {STYLE_LABELS[k]}
          </button>
        ))}
      </div>

      {/* Right-side tool dock */}
      <div className="absolute right-4 top-4 flex flex-col gap-2">
        <ToolButton
          active={traffic}
          onClick={() => setTraffic((v) => !v)}
          label="Traffic"
          icon={<CarFront className="size-4" />}
        />
        <ToolButton
          active={drawMode === "polygon"}
          onClick={() => setDrawMode((m) => (m === "polygon" ? "none" : "polygon"))}
          label="Polygon"
          icon={<PenTool className="size-4" />}
        />
        <ToolButton
          active={drawMode === "circle"}
          onClick={() => setDrawMode((m) => (m === "circle" ? "none" : "circle"))}
          label="Radius"
          icon={<CircleIcon className="size-4" />}
        />
        <ToolButton onClick={openStreetView} label="Street view" icon={<Eye className="size-4" />} />
        <ToolButton onClick={geolocate} label="My location" icon={<Navigation className="size-4" />} />
        {overlaysRef.current.length > 0 && (
          <ToolButton onClick={clearOverlays} label="Clear" icon={<Trash2 className="size-4" />} />
        )}
      </div>

      {/* Count badge */}
      {showCountBadge && (
        <div className="glass absolute bottom-4 left-4 rounded-2xl px-3 py-2 text-xs text-foreground/85 shadow-soft">
          <span className="font-semibold text-foreground">{properties.length.toLocaleString()}</span> listings on map
        </div>
      )}
    </div>
  );
}

function ToolButton({
  active,
  onClick,
  label,
  icon,
}: {
  active?: boolean;
  onClick: () => void;
  label: string;
  icon: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className={`glass flex size-10 items-center justify-center rounded-xl shadow-soft transition ${
        active ? "bg-primary text-primary-foreground" : "text-foreground/80 hover:text-foreground"
      }`}
    >
      {icon}
    </button>
  );
}

function bboxFromBounds(bounds: google.maps.LatLngBounds): BoundsBox {
  const ne = bounds.getNorthEast();
  const sw = bounds.getSouthWest();
  return { west: sw.lng(), south: sw.lat(), east: ne.lng(), north: ne.lat() };
}

function infoWindowHtml(p: Property): string {
  const img = p.media[0]?.url ?? "";
  const price = formatPriceWithUnit(p.price, p.currency, p.listing_type);
  return `
    <div style="font-family:Inter,system-ui;min-width:220px;max-width:260px">
      ${img ? `<img src="${img}" alt="" style="width:100%;height:120px;object-fit:cover;border-radius:8px;margin-bottom:8px"/>` : ""}
      <div style="font-weight:700;font-size:13px;color:#1B1F4A;line-height:1.3">${escapeHtml(p.title)}</div>
      <div style="font-size:11px;color:#5e637a;margin-top:2px">${escapeHtml(p.city)}, ${escapeHtml(p.country)}</div>
      <div style="font-size:14px;font-weight:700;color:#2D3270;margin-top:6px">${price}</div>
      <a href="/properties/${p.slug}" style="display:inline-block;margin-top:8px;font-size:12px;font-weight:600;color:#2D3270;text-decoration:none">View details →</a>
    </div>`;
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]!));
}
