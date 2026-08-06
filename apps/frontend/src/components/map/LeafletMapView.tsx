/**
 * Premium, keyless map surface for ActiveHome — OpenStreetMap tiles via Leaflet.
 *
 * Replaces `GoogleMapView`/`MapView` (Mapbox): both needed accounts/keys this app doesn't own
 * (the Google Maps browser key belonged to Lovable-managed infra with a `RefererNotAllowedMapError`
 * nobody here can fix; Mapbox GL JS requires an access token for its hosted styles). Leaflet +
 * OSM/Esri/OpenTopoMap tiles and OSRM's public routing demo (`@/lib/routing`) need no key and no
 * allow-listed referrer at all.
 *
 * Generic `MapMarker` API (not tied to any one domain type) so the same component drives the
 * global /map search, the homepage preview, a single property's location card, and a recreation
 * venue's booking modal.
 *
 * Feature set:
 *  - Street / Satellite / Terrain tile layers, plus a "Street View" entry that deep-links to
 *    Yandex Maps' own panorama viewer for the focused point (no embed, no key -- just a normal
 *    outbound link, the same way a "open in Yandex Maps" button would work). Yandex's own JS API
 *    would need a registered API key (the exact problem that took down the old Google Maps
 *    integration) so the embedded map itself stays on keyless OSM/Esri/OpenTopoMap tiles.
 *  - Marker clustering (leaflet.markercluster) with a custom premium bubble icon.
 *  - `focus` prop flies/zooms the map to a marker (revealing it out of a cluster if needed) --
 *    this is what makes "select a listing -> map jumps to it" actually work; the previous version
 *    only read `center`/`zoom` at mount time and silently ignored later prop changes.
 *  - "Yo'lni boshlash": real turn-by-turn navigation via OSRM, with live position tracking
 *    (geolocation watch), a step list that auto-advances as the user nears each maneuver, and a
 *    animated location puck.
 *  - Hand-rolled polygon/radius area-search tools (unchanged from the previous version).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ClientOnly } from "@tanstack/react-router";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "leaflet.markercluster/dist/MarkerCluster.css";
import {
  Layers,
  Navigation,
  PenTool,
  Circle as CircleIcon,
  Trash2,
  Maximize2,
  Minimize2,
  LocateFixed,
  ExternalLink,
  X,
  Flag,
  RotateCw,
  CornerUpRight,
  CornerUpLeft,
  CornerDownRight,
  CornerDownLeft,
  ArrowUp,
  ArrowUpRight as ArrowUpRightIcon,
  ArrowUpLeft,
  Undo2,
  Loader2,
  Map as MapIcon,
  Satellite,
  Mountain,
  Search,
  MapPin,
  Car,
  Footprints,
  Bus,
  type LucideIcon,
} from "lucide-react";
import {
  fetchRoute,
  formatDistance,
  formatDuration,
  distanceMeters,
  transitDirectionsUrl,
  RoutingError,
  type RouteResult,
  type RouteStep,
  type TravelMode,
} from "@/lib/routing";
import { searchPlaces, type GeocodeResult } from "@/lib/geocoding";

type StyleKey = "street" | "satellite" | "terrain";

const TILE_LAYERS: Record<StyleKey, { url: string; attribution: string; maxZoom: number }> = {
  street: {
    url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    maxZoom: 19,
  },
  satellite: {
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attribution: "Tiles &copy; Esri",
    maxZoom: 19,
  },
  terrain: {
    url: "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
    attribution:
      '&copy; OpenStreetMap contributors, SRTM | &copy; <a href="https://opentopomap.org">OpenTopoMap</a>',
    maxZoom: 17,
  },
};

const STYLE_META: Record<StyleKey, { label: string; Icon: LucideIcon }> = {
  street: { label: "Standart", Icon: MapIcon },
  satellite: { label: "Sun'iy yo'ldosh", Icon: Satellite },
  terrain: { label: "Relyef", Icon: Mountain },
};

export interface MapMarker {
  id: string;
  lat: number;
  lng: number;
  /** Short text on the pin itself (price, venue type, ...). */
  label: string;
  title: string;
  subtitle?: string;
  image?: string;
  href?: string;
  /** Drives the filter chip bar (`filterOptions`/`activeFilterKeys`) -- purely a grouping key, the
   * map doesn't attach any meaning to it. */
  category?: string;
  /** Hex color tinting this pin when unselected (falls back to the theme default when unset). */
  accent?: string;
}

export interface FilterOption {
  key: string;
  label: string;
  accent?: string;
}

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

interface FocusTarget {
  id?: string;
  lat: number;
  lng: number;
  zoom?: number;
}

interface NavState {
  target: MapMarker;
  mode: TravelMode;
  phase: "locating" | "routing" | "active" | "error";
  route?: RouteResult;
  activeStep: number;
  error?: string;
  userPos?: { lat: number; lng: number; heading?: number | null };
}

const MODE_META: Record<TravelMode, { label: string; Icon: LucideIcon }> = {
  driving: { label: "Avtomobil", Icon: Car },
  walking: { label: "Piyoda", Icon: Footprints },
};

interface Props {
  markers: MapMarker[];
  center?: { lat: number; lng: number };
  zoom?: number;
  /** Set (to a new object) whenever the caller wants the map to jump to a point -- e.g. the user
   * clicked a listing in a side list. Unlike `center`/`zoom`, this is read on every change, not
   * just at mount. */
  focus?: FocusTarget | null;
  height?: string;
  className?: string;
  onSelect?: (m: MapMarker) => void;
  onAreaSearch?: (area: AreaSearch) => void;
  /** Fired when the user picks a place from the location search box -- e.g. the /map page uses
   * this to fetch and show every listing (across categories) near the searched place. */
  onPlaceSearch?: (result: GeocodeResult) => void;
  showCountBadge?: boolean;
  /** Hides the polygon/radius area-search dock -- off for single-marker embeds (property page,
   * recreation venue modal) where "search this area" makes no sense. */
  enableDrawTools?: boolean;
  /** Hides the location search box -- on by default, off for tight single-marker embeds. */
  enableSearch?: boolean;
  /** Category chip bar rendered inside the search panel. The map only renders the chips and
   * reports the active key set back up -- filtering the `markers` array by category is the
   * caller's job (the map itself has no idea what a "category" means). */
  filterOptions?: FilterOption[];
  activeFilterKeys?: string[];
  onFilterKeysChange?: (keys: string[]) => void;
}

function escapeHtml(s: string): string {
  return s.replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!,
  );
}

function pinIcon(marker: MapMarker, selected: boolean): L.DivIcon {
  const accentStyle =
    !selected && marker.accent
      ? ` style="background:${marker.accent};border-color:${marker.accent};color:#fff"`
      : "";
  return L.divIcon({
    className: "",
    html: `<div class="ah-pin${selected ? " ah-pin--selected" : ""}"${accentStyle}>${escapeHtml(marker.label)}</div>`,
    iconSize: [0, 0],
  });
}

function popupHtml(m: MapMarker): string {
  return `
    <div style="font-family:var(--font-sans);min-width:200px;max-width:240px">
      ${m.image ? `<img src="${m.image}" alt="" style="width:100%;height:110px;object-fit:cover;border-radius:10px;margin-bottom:8px"/>` : ""}
      <div style="font-weight:700;font-size:13px;color:var(--foreground);line-height:1.3">${escapeHtml(m.title)}</div>
      ${m.subtitle ? `<div style="font-size:11px;color:var(--muted-foreground);margin-top:2px">${escapeHtml(m.subtitle)}</div>` : ""}
      <div style="font-size:14px;font-weight:700;color:var(--primary);margin-top:6px">${escapeHtml(m.label)}</div>
      <div style="display:flex;gap:6px;margin-top:10px">
        <button data-ah-action="navigate" style="flex:1;display:inline-flex;align-items:center;justify-content:center;gap:5px;border-radius:999px;background:var(--primary);color:var(--primary-foreground);font-size:12px;font-weight:600;padding:7px 10px;border:none;cursor:pointer">Yo'lni boshlash</button>
        ${m.href ? `<a href="${m.href}" style="display:inline-flex;align-items:center;justify-content:center;border-radius:999px;border:1px solid var(--border);color:var(--foreground);font-size:12px;font-weight:600;padding:7px 12px;text-decoration:none;white-space:nowrap">Batafsil</a>` : ""}
      </div>
    </div>`;
}

function bboxFromLatLngBounds(bounds: L.LatLngBounds): BoundsBox {
  return {
    west: bounds.getWest(),
    south: bounds.getSouth(),
    east: bounds.getEast(),
    north: bounds.getNorth(),
  };
}

/** Deep-links to Yandex Maps' own panorama viewer for the point -- no embed, no key, just an
 * outbound link (same as the old Google Street View button, swapped per product direction). */
function streetViewUrl(lat: number, lng: number): string {
  return `https://yandex.com/maps/?panorama%5Bpoint%5D=${lng},${lat}&panorama%5Bdirection%5D=180,0&z=17`;
}

function stepIcon(step: RouteStep): LucideIcon {
  if (step.maneuverType === "arrive") return Flag;
  if (step.maneuverType === "depart") return Navigation;
  if (step.maneuverType.includes("roundabout") || step.maneuverType.includes("rotary"))
    return RotateCw;
  switch (step.maneuverModifier) {
    case "uturn":
      return Undo2;
    case "sharp left":
      return CornerDownLeft;
    case "left":
      return CornerUpLeft;
    case "slight left":
      return ArrowUpLeft;
    case "sharp right":
      return CornerDownRight;
    case "right":
      return CornerUpRight;
    case "slight right":
      return ArrowUpRightIcon;
    default:
      return ArrowUp;
  }
}

export function LeafletMapView(props: Props) {
  return (
    <ClientOnly
      fallback={<MapSkeleton height={props.height ?? "70vh"} className={props.className} />}
    >
      <LeafletMapViewClient {...props} />
    </ClientOnly>
  );
}

function MapSkeleton({ height, className = "" }: { height: string; className?: string }) {
  return (
    <div
      className={`relative overflow-hidden rounded-3xl border border-border bg-card shadow-elevated ${className}`}
      style={{ height }}
    >
      <div className="absolute inset-0 animate-pulse bg-primary/5" />
    </div>
  );
}

function LeafletMapViewClient({
  markers,
  center = { lat: 41.3111, lng: 69.2797 },
  zoom = 3,
  focus = null,
  height = "70vh",
  className = "",
  onSelect,
  onAreaSearch,
  onPlaceSearch,
  showCountBadge = true,
  enableDrawTools = true,
  enableSearch = true,
  filterOptions,
  activeFilterKeys,
  onFilterKeysChange,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const tileLayerRef = useRef<L.TileLayer | null>(null);
  const clusterRef = useRef<L.MarkerClusterGroup | null>(null);
  const markersByIdRef = useRef<Map<string, L.Marker>>(new Map());
  const overlaysRef = useRef<Array<L.Polygon | L.Circle>>([]);
  const routeLayersRef = useRef<{ casing: L.Polyline; line: L.Polyline } | null>(null);
  const puckRef = useRef<L.Marker | null>(null);
  const searchMarkerRef = useRef<L.Marker | null>(null);
  const routeFittedRef = useRef<string | null>(null);
  const drawStateRef = useRef<{
    mode: "none" | "polygon" | "circle";
    points: L.LatLng[];
    tempLayer: L.Polygon | L.Circle | L.Polyline | null;
    circleCenter: L.LatLng | null;
    dragging: boolean;
  }>({ mode: "none", points: [], tempLayer: null, circleCenter: null, dragging: false });

  const [style, setStyle] = useState<StyleKey>("street");
  const [layersOpen, setLayersOpen] = useState(false);
  const [drawMode, setDrawMode] = useState<"none" | "polygon" | "circle">("none");
  const [overlayCount, setOverlayCount] = useState(0);
  const [fullscreen, setFullscreen] = useState(false);
  const [nav, setNav] = useState<NavState | null>(null);
  const [navCollapsed, setNavCollapsed] = useState(false);
  const stepListRef = useRef<HTMLDivElement | null>(null);

  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<GeocodeResult[]>([]);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);

  // Debounced Nominatim lookup -- fires ~350ms after the user stops typing.
  useEffect(() => {
    if (!enableSearch) return;
    const q = searchQuery.trim();
    if (q.length < 2) {
      setSearchResults([]);
      setSearchLoading(false);
      return;
    }
    setSearchLoading(true);
    const timer = setTimeout(async () => {
      const results = await searchPlaces(q);
      setSearchResults(results);
      setSearchLoading(false);
    }, 350);
    return () => clearTimeout(timer);
  }, [searchQuery, enableSearch]);

  const selectPlace = useCallback(
    (result: GeocodeResult) => {
      const map = mapRef.current;
      setSearchQuery(result.label);
      setSearchOpen(false);
      if (map) {
        if (result.boundingBox) {
          map.flyToBounds(
            [
              [result.boundingBox.south, result.boundingBox.west],
              [result.boundingBox.north, result.boundingBox.east],
            ],
            { duration: 1, padding: [40, 40] },
          );
        } else {
          map.flyTo([result.lat, result.lng], 14, { duration: 1 });
        }
        searchMarkerRef.current?.remove();
        searchMarkerRef.current = L.marker([result.lat, result.lng], {
          icon: L.divIcon({
            className: "",
            html: `<div class="ah-search-pin"></div>`,
            iconSize: [0, 0],
          }),
        }).addTo(map);
      }
      onPlaceSearch?.(result);
    },
    [onPlaceSearch],
  );

  // Init map once. `leaflet.markercluster` is dynamically imported (not a static top-level
  // import) because its UMD build reaches for a global `L` that doesn't exist during SSR --
  // ClientOnly defers *rendering* this component server-side, but a static side-effect import
  // still gets evaluated during SSR module loading regardless, which crashed the route.
  const [mapReady, setMapReady] = useState(false);
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    let cancelled = false;

    (async () => {
      await import("leaflet.markercluster");
      if (cancelled || !containerRef.current || mapRef.current) return;

      const map = L.map(containerRef.current, {
        center: [center.lat, center.lng],
        zoom,
        zoomControl: true,
        attributionControl: true,
      });
      map.zoomControl.setPosition("bottomright");

      const layer = TILE_LAYERS.street;
      tileLayerRef.current = L.tileLayer(layer.url, {
        attribution: layer.attribution,
        maxZoom: layer.maxZoom,
      }).addTo(map);

      const cluster = L.markerClusterGroup({
        maxClusterRadius: 56,
        spiderfyOnMaxZoom: true,
        showCoverageOnHover: false,
        iconCreateFunction: (c) =>
          L.divIcon({
            className: "",
            html: `<div class="ah-cluster">${c.getChildCount()}</div>`,
            iconSize: [42, 42],
          }),
      });
      cluster.addTo(map);
      clusterRef.current = cluster;
      mapRef.current = map;
      setMapReady(true);
    })();

    return () => {
      cancelled = true;
      mapRef.current?.remove();
      mapRef.current = null;
      tileLayerRef.current = null;
      clusterRef.current = null;
      markersByIdRef.current.clear();
      searchMarkerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Style switching.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    tileLayerRef.current?.remove();
    const layer = TILE_LAYERS[style];
    tileLayerRef.current = L.tileLayer(layer.url, {
      attribution: layer.attribution,
      maxZoom: layer.maxZoom,
    }).addTo(map);
  }, [style]);

  const routeTo = useCallback(
    async (userPos: { lat: number; lng: number }, target: MapMarker, mode: TravelMode) => {
      setNav((n) => (n ? { ...n, phase: "routing", mode } : n));
      try {
        const route = await fetchRoute(userPos, { lat: target.lat, lng: target.lng }, mode);
        setNav((n) =>
          n && n.target.id === target.id ? { ...n, phase: "active", route, activeStep: 0 } : n,
        );
      } catch (err) {
        setNav((n) =>
          n
            ? {
                ...n,
                phase: "error",
                error: err instanceof RoutingError ? err.message : "Xatolik yuz berdi.",
              }
            : n,
        );
      }
    },
    [],
  );

  const startNavigation = useCallback(
    (target: MapMarker) => {
      setNav({ target, mode: "driving", phase: "locating", activeStep: 0 });
      if (!navigator.geolocation) {
        setNav((n) =>
          n ? { ...n, phase: "error", error: "Brauzeringiz joylashuvni aniqlay olmaydi." } : n,
        );
        return;
      }
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          const userPos = {
            lat: pos.coords.latitude,
            lng: pos.coords.longitude,
            heading: pos.coords.heading,
          };
          setNav((n) => (n ? { ...n, userPos } : n));
          void routeTo(userPos, target, "driving");
        },
        () => {
          setNav((n) => (n ? { ...n, phase: "error", error: "Joylashuvga ruxsat berilmadi." } : n));
        },
        { enableHighAccuracy: true, timeout: 10000 },
      );
    },
    [routeTo],
  );

  const stopNavigation = useCallback(() => {
    setNav(null);
    routeFittedRef.current = null;
  }, []);

  const switchTravelMode = useCallback(
    (mode: TravelMode) => {
      setNav((n) => {
        if (!n) return n;
        if (n.userPos) void routeTo(n.userPos, n.target, mode);
        return { ...n, mode, phase: n.userPos ? "routing" : n.phase };
      });
    },
    [routeTo],
  );

  const openTransit = useCallback(() => {
    setNav((n) => {
      if (!n?.userPos) return n;
      window.open(
        transitDirectionsUrl(n.userPos, { lat: n.target.lat, lng: n.target.lng }),
        "_blank",
        "noopener,noreferrer",
      );
      return n;
    });
  }, []);

  // Markers (clustered). Popup wires a raw <button> via a delegated `popupopen` listener since
  // Leaflet popups are plain HTML strings, not React trees.
  useEffect(() => {
    const cluster = clusterRef.current;
    if (!cluster) return;

    cluster.clearLayers();
    markersByIdRef.current.clear();

    const leafletMarkers = markers.map((m) => {
      const marker = L.marker([m.lat, m.lng], { icon: pinIcon(m, false) });
      marker.bindPopup(popupHtml(m), { closeButton: true, maxWidth: 260 });
      marker.on("popupopen", (e) => {
        const el = (e.popup as L.Popup).getElement();
        const btn = el?.querySelector<HTMLButtonElement>('[data-ah-action="navigate"]');
        btn?.addEventListener("click", () => startNavigation(m));
      });
      marker.on("click", () => {
        markersByIdRef.current.forEach((mk, id) => {
          const src = markers.find((mm) => mm.id === id);
          if (src) mk.setIcon(pinIcon(src, id === m.id));
        });
        onSelect?.(m);
      });
      markersByIdRef.current.set(m.id, marker);
      return marker;
    });

    cluster.addLayers(leafletMarkers);

    return () => {
      cluster.clearLayers();
      markersByIdRef.current.clear();
    };
  }, [markers, onSelect, startNavigation, mapReady]);

  // Focus -- flies to (and reveals out of a cluster, if needed) a specific point on demand.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !focus) return;
    const marker = focus.id ? markersByIdRef.current.get(focus.id) : undefined;
    if (marker && clusterRef.current) {
      clusterRef.current.zoomToShowLayer(marker, () => {
        map.flyTo([focus.lat, focus.lng], focus.zoom ?? Math.max(map.getZoom(), 14), {
          duration: 0.9,
        });
        marker.openPopup();
      });
    } else {
      map.flyTo([focus.lat, focus.lng], focus.zoom ?? 14, { duration: 1.1 });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus?.id, focus?.lat, focus?.lng, focus?.zoom, mapReady]);

  // Drawing tools -- hand-rolled on Leaflet's own mouse events (no plugin dependency).
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const state = drawStateRef.current;
    state.mode = drawMode;
    state.points = [];
    state.circleCenter = null;
    state.dragging = false;
    if (state.tempLayer) {
      state.tempLayer.remove();
      state.tempLayer = null;
    }
    if (drawMode === "none") {
      map.dragging.enable();
      return;
    }
    map.dragging.disable();

    const finishPolygon = () => {
      if (state.points.length >= 3) {
        const poly = L.polygon(state.points, {
          color: "var(--primary)",
          weight: 2,
          fillColor: "var(--primary)",
          fillOpacity: 0.15,
        }).addTo(map);
        overlaysRef.current.push(poly);
        setOverlayCount(overlaysRef.current.length);
        onAreaSearch?.({ kind: "polygon", bbox: bboxFromLatLngBounds(poly.getBounds()) });
      }
      state.tempLayer?.remove();
      state.tempLayer = null;
      state.points = [];
      setDrawMode("none");
    };

    const onClick = (e: L.LeafletMouseEvent) => {
      if (state.mode !== "polygon") return;
      state.points.push(e.latlng);
      state.tempLayer?.remove();
      state.tempLayer = L.polyline(state.points, {
        color: "var(--primary)",
        weight: 2,
        dashArray: "4 4",
      }).addTo(map);
    };
    const onDblClick = (e: L.LeafletMouseEvent) => {
      if (state.mode !== "polygon") return;
      L.DomEvent.stop(e);
      finishPolygon();
    };
    const onMouseDown = (e: L.LeafletMouseEvent) => {
      if (state.mode !== "circle") return;
      state.circleCenter = e.latlng;
      state.dragging = true;
      state.tempLayer = L.circle(e.latlng, {
        radius: 1,
        color: "var(--primary)",
        weight: 2,
        fillColor: "var(--primary)",
        fillOpacity: 0.12,
      }).addTo(map);
    };
    const onMouseMove = (e: L.LeafletMouseEvent) => {
      if (state.mode !== "circle" || !state.dragging || !state.circleCenter) return;
      const radius = state.circleCenter.distanceTo(e.latlng);
      (state.tempLayer as L.Circle | null)?.setRadius(radius);
    };
    const onMouseUp = () => {
      if (state.mode !== "circle" || !state.dragging || !state.circleCenter) return;
      state.dragging = false;
      const circle = state.tempLayer as L.Circle | null;
      state.tempLayer = null;
      if (circle && circle.getRadius() > 20) {
        overlaysRef.current.push(circle);
        setOverlayCount(overlaysRef.current.length);
        const c = circle.getLatLng();
        onAreaSearch?.({
          kind: "circle",
          bbox: bboxFromLatLngBounds(circle.getBounds()),
          center: { lat: c.lat, lng: c.lng },
          radiusMeters: circle.getRadius(),
        });
      } else {
        circle?.remove();
      }
      setDrawMode("none");
    };

    map.on("click", onClick);
    map.on("dblclick", onDblClick);
    map.on("mousedown", onMouseDown);
    map.on("mousemove", onMouseMove);
    map.on("mouseup", onMouseUp);

    return () => {
      map.off("click", onClick);
      map.off("dblclick", onDblClick);
      map.off("mousedown", onMouseDown);
      map.off("mousemove", onMouseMove);
      map.off("mouseup", onMouseUp);
      map.dragging.enable();
    };
  }, [drawMode, onAreaSearch]);

  // Live position tracking for the active navigation session.
  const navTargetId = nav?.target.id ?? null;
  useEffect(() => {
    if (!navTargetId || !navigator.geolocation) return;
    const id = navigator.geolocation.watchPosition(
      (pos) => {
        const p = {
          lat: pos.coords.latitude,
          lng: pos.coords.longitude,
          heading: pos.coords.heading,
        };
        setNav((n) => {
          if (!n) return n;
          let activeStep = n.activeStep;
          const nextStep = n.route?.steps[activeStep + 1];
          if (nextStep && distanceMeters(p, nextStep.location) < 40) activeStep += 1;
          return { ...n, userPos: p, activeStep };
        });
      },
      (err) => console.warn("[nav watch]", err.message),
      { enableHighAccuracy: true, maximumAge: 2000, timeout: 15000 },
    );
    return () => navigator.geolocation.clearWatch(id);
  }, [navTargetId]);

  // Route polyline (casing + colored line) + one-time fitBounds when a route first arrives.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    routeLayersRef.current?.casing.remove();
    routeLayersRef.current?.line.remove();
    routeLayersRef.current = null;

    if (!nav?.route) return;
    const latlngs = nav.route.coordinates.map((c) => [c.lat, c.lng] as [number, number]);
    const casing = L.polyline(latlngs, {
      color: "#0b0e2b",
      weight: 8,
      opacity: 0.35,
      lineCap: "round",
    }).addTo(map);
    const line = L.polyline(latlngs, {
      color: "var(--primary)",
      weight: 5,
      opacity: 0.95,
      lineCap: "round",
    }).addTo(map);
    routeLayersRef.current = { casing, line };

    const fitKey = `${nav.target.id}:${nav.mode}`;
    if (routeFittedRef.current !== fitKey) {
      map.fitBounds(line.getBounds(), { padding: [64, 64] });
      routeFittedRef.current = fitKey;
    }

    return () => {
      casing.remove();
      line.remove();
    };
  }, [nav?.route, nav?.target.id, nav?.mode]);

  // Live location puck.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !nav?.userPos) {
      puckRef.current?.remove();
      puckRef.current = null;
      return;
    }
    const { lat, lng, heading } = nav.userPos;
    const rotation = typeof heading === "number" && !Number.isNaN(heading) ? heading : 0;
    const icon = L.divIcon({
      className: "",
      html: `<div class="ah-puck" style="transform:rotate(${rotation}deg)"><span class="ah-puck__cone"></span><span class="ah-puck__ring"></span><span class="ah-puck__dot"></span></div>`,
      iconSize: [18, 18],
      iconAnchor: [9, 9],
    });
    if (puckRef.current) {
      puckRef.current.setLatLng([lat, lng]);
      puckRef.current.setIcon(icon);
    } else {
      puckRef.current = L.marker([lat, lng], { icon, zIndexOffset: 1000 }).addTo(map);
    }
  }, [nav?.userPos]);

  // Auto-scroll the step list to keep the active step in view.
  useEffect(() => {
    if (!nav || nav.phase !== "active") return;
    const container = stepListRef.current;
    const activeEl = container?.querySelector<HTMLElement>(`[data-step="${nav.activeStep}"]`);
    activeEl?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [nav?.activeStep, nav?.phase]);

  const recenterOnUser = () => {
    if (!nav?.userPos || !mapRef.current) return;
    mapRef.current.flyTo([nav.userPos.lat, nav.userPos.lng], 17, { duration: 0.8 });
  };

  const clearOverlays = () => {
    overlaysRef.current.forEach((o) => o.remove());
    overlaysRef.current = [];
    setOverlayCount(0);
  };

  const geolocate = () => {
    if (!navigator.geolocation || !mapRef.current) return;
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        mapRef.current?.flyTo([pos.coords.latitude, pos.coords.longitude], 13, { duration: 1 });
      },
      (err) => console.warn("[geolocation]", err.message),
      { enableHighAccuracy: true, timeout: 8000 },
    );
  };

  const openStreetView = () => {
    const map = mapRef.current;
    const c = map ? map.getCenter() : center;
    window.open(streetViewUrl(c.lat, c.lng), "_blank", "noopener,noreferrer");
  };

  const containerStyle = useMemo(
    () => ({ height: fullscreen ? "100vh" : height }),
    [height, fullscreen],
  );

  return (
    <div
      className={`relative transition-[border-radius] ${fullscreen ? "fixed inset-0 z-[999]" : className}`}
      style={containerStyle}
    >
      {/* The rounded/clipped map surface lives in its own layer so overlay UI (search results,
       * the layers menu, the nav panel) can extend past its bounds without being cut off by the
       * `overflow-hidden` that crops the Leaflet tiles into rounded corners. */}
      <div
        className={`absolute inset-0 overflow-hidden border border-border bg-card shadow-elevated ${
          fullscreen ? "rounded-none" : "rounded-3xl"
        }`}
      >
        <div ref={containerRef} className="absolute inset-0" />
      </div>

      {/* Top overlay row: layer switcher, search, and the tool dock all live in one flex row so
       * they always share the available width and never overlap each other, at any viewport size. */}
      <div className="absolute inset-x-0 top-0 z-[500] flex items-start justify-between gap-2 p-3 sm:p-4">
        {/* Layer switcher -- an icon trigger (matches the tool dock's own buttons) with a dropdown
         * panel, so it never needs its own reserved width on narrow screens. */}
        <div className="relative shrink-0">
          <ToolButton
            active={layersOpen}
            onClick={() => setLayersOpen((v) => !v)}
            label="Xarita ko'rinishi"
            icon={<Layers className="size-4" />}
          />
          {layersOpen && (
            <div className="glass absolute left-0 top-full z-10 mt-2 w-48 overflow-hidden rounded-2xl shadow-elevated">
              <div className="p-1">
                {(Object.keys(STYLE_META) as StyleKey[]).map((k) => {
                  const Meta = STYLE_META[k];
                  return (
                    <button
                      key={k}
                      onClick={() => {
                        setStyle(k);
                        setLayersOpen(false);
                      }}
                      className={`flex w-full items-center gap-2 rounded-xl px-2.5 py-2 text-left text-xs font-medium transition ${
                        style === k
                          ? "bg-primary text-primary-foreground shadow-soft"
                          : "text-foreground/80 hover:bg-card/60"
                      }`}
                    >
                      <Meta.Icon className="size-3.5" />
                      {Meta.label}
                    </button>
                  );
                })}
                <button
                  onClick={() => {
                    openStreetView();
                    setLayersOpen(false);
                  }}
                  className="flex w-full items-center gap-2 rounded-xl px-2.5 py-2 text-left text-xs font-medium text-foreground/80 hover:bg-card/60"
                >
                  <ExternalLink className="size-3.5" />
                  Ko'cha ko'rinishi
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Location search -- flexible middle column, so it takes exactly whatever width is left
         * over between the layer switcher and the tool dock instead of a fixed/centered width
         * that could collide with either at in-between viewport sizes. */}
        {enableSearch ? (
          <div className="glass min-w-0 max-w-md flex-1 overflow-hidden rounded-2xl shadow-soft">
            <div className="flex items-center gap-2 px-3 py-2.5">
              <Search className="size-3.5 shrink-0 text-muted-foreground" />
              <input
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setSearchOpen(true);
                }}
                onFocus={() => setSearchOpen(true)}
                onBlur={() => setTimeout(() => setSearchOpen(false), 150)}
                placeholder="Hudud, manzil yoki joy nomini qidiring…"
                className="min-w-0 flex-1 bg-transparent text-xs text-foreground placeholder:text-muted-foreground/70 focus:outline-none"
              />
              {searchLoading && (
                <Loader2 className="size-3.5 shrink-0 animate-spin text-muted-foreground" />
              )}
            </div>
            {filterOptions && filterOptions.length > 0 && (
              <div className="scrollbar-none flex gap-1.5 overflow-x-auto border-t border-border/60 px-2.5 py-2">
                <button
                  onClick={() => onFilterKeysChange?.([])}
                  className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold transition ${
                    !activeFilterKeys?.length
                      ? "bg-primary text-primary-foreground"
                      : "bg-card/60 text-foreground/70 hover:bg-card"
                  }`}
                >
                  Barchasi
                </button>
                {filterOptions.map((f) => {
                  const active = !!activeFilterKeys?.includes(f.key);
                  return (
                    <button
                      key={f.key}
                      onClick={() =>
                        onFilterKeysChange?.(
                          active
                            ? (activeFilterKeys ?? []).filter((k) => k !== f.key)
                            : [...(activeFilterKeys ?? []), f.key],
                        )
                      }
                      className={`shrink-0 inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold transition ${
                        active ? "text-white" : "bg-card/60 text-foreground/70 hover:bg-card"
                      }`}
                      style={active ? { background: f.accent || "var(--primary)" } : undefined}
                    >
                      <span
                        className="size-1.5 rounded-full"
                        style={{ background: f.accent || "var(--primary)" }}
                      />
                      {f.label}
                    </button>
                  );
                })}
              </div>
            )}
            {searchOpen && searchResults.length > 0 && (
              <div className="max-h-64 overflow-y-auto border-t border-border/60 p-1">
                {searchResults.map((r) => (
                  <button
                    key={r.id}
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => selectPlace(r)}
                    className="flex w-full items-start gap-2 rounded-xl px-2.5 py-2 text-left transition hover:bg-card/60"
                  >
                    <MapPin className="mt-0.5 size-3.5 shrink-0 text-primary" />
                    <div className="min-w-0">
                      <div className="truncate text-xs font-semibold text-foreground">
                        {r.label}
                      </div>
                      {r.secondary && (
                        <div className="truncate text-[11px] text-muted-foreground">
                          {r.secondary}
                        </div>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="flex-1" aria-hidden />
        )}

        {/* Right-side tool dock */}
        <div className="flex shrink-0 flex-col gap-2">
          <ToolButton
            onClick={() => setFullscreen((v) => !v)}
            label={fullscreen ? "Kichraytirish" : "To'liq ekran"}
            icon={fullscreen ? <Minimize2 className="size-4" /> : <Maximize2 className="size-4" />}
          />
          <ToolButton
            onClick={geolocate}
            label="Mening joylashuvim"
            icon={<LocateFixed className="size-4" />}
          />
          {enableDrawTools && (
            <>
              <ToolButton
                active={drawMode === "polygon"}
                onClick={() => setDrawMode((m) => (m === "polygon" ? "none" : "polygon"))}
                label="Ko'pburchak (bosing, oxirida ikki marta bosing)"
                icon={<PenTool className="size-4" />}
              />
              <ToolButton
                active={drawMode === "circle"}
                onClick={() => setDrawMode((m) => (m === "circle" ? "none" : "circle"))}
                label="Radius (bosib torting)"
                icon={<CircleIcon className="size-4" />}
              />
              {overlayCount > 0 && (
                <ToolButton
                  onClick={clearOverlays}
                  label="Tozalash"
                  icon={<Trash2 className="size-4" />}
                />
              )}
            </>
          )}
        </div>
      </div>

      {/* Count badge */}
      {showCountBadge && !nav && (
        <div className="glass absolute bottom-4 left-4 z-[500] rounded-2xl px-3 py-2 text-xs text-foreground/85 shadow-soft">
          <span className="font-semibold text-foreground">{markers.length.toLocaleString()}</span>{" "}
          xaritadagi natija
        </div>
      )}

      {/* Navigation panel */}
      {nav && (
        <div className="absolute inset-x-0 bottom-0 z-[600] flex justify-center px-3 pb-3 sm:px-4 sm:pb-4">
          <div className="glass w-full max-w-xl overflow-hidden rounded-3xl shadow-elevated">
            <div className="flex items-center gap-3 px-4 py-3.5">
              <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary/12 text-primary">
                <Navigation className="size-4" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-semibold text-foreground">
                  {nav.target.title}
                </div>
                <div className="text-xs text-muted-foreground">
                  {nav.phase === "locating" && "Joylashuvingiz aniqlanmoqda…"}
                  {nav.phase === "routing" && "Marshrut hisoblanmoqda…"}
                  {nav.phase === "active" && nav.route && (
                    <>
                      {formatDistance(nav.route.distanceMeters)} ·{" "}
                      {formatDuration(nav.route.durationSeconds)}
                    </>
                  )}
                  {nav.phase === "error" && <span className="text-destructive">{nav.error}</span>}
                </div>
              </div>
              {(nav.phase === "locating" || nav.phase === "routing") && (
                <Loader2 className="size-4 shrink-0 animate-spin text-muted-foreground" />
              )}
              {nav.phase === "active" && (
                <button
                  onClick={recenterOnUser}
                  aria-label="Joylashuvimga qaytish"
                  className="flex size-8 shrink-0 items-center justify-center rounded-full border border-border text-foreground/70 transition hover:bg-muted"
                >
                  <LocateFixed className="size-3.5" />
                </button>
              )}
              {nav.phase === "active" && nav.route && (
                <button
                  onClick={() => setNavCollapsed((v) => !v)}
                  className="shrink-0 rounded-full border border-border px-2 py-1 text-[10px] font-semibold text-foreground/70 transition hover:bg-muted"
                >
                  {navCollapsed ? "Yozish" : "Yig'ish"}
                </button>
              )}
              <button
                onClick={stopNavigation}
                aria-label="Yo'lni tugatish"
                className="flex size-8 shrink-0 items-center justify-center rounded-full border border-border text-foreground/70 transition hover:bg-destructive/10 hover:text-destructive"
              >
                <X className="size-3.5" />
              </button>
            </div>

            {nav.phase !== "locating" && (
              <div className="flex items-center gap-1.5 border-t border-border/60 px-4 py-2">
                {(Object.keys(MODE_META) as TravelMode[]).map((m) => {
                  const Meta = MODE_META[m];
                  return (
                    <button
                      key={m}
                      onClick={() => switchTravelMode(m)}
                      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[11px] font-semibold transition ${
                        nav.mode === m
                          ? "bg-primary text-primary-foreground shadow-soft"
                          : "text-foreground/70 hover:bg-muted"
                      }`}
                    >
                      <Meta.Icon className="size-3.5" />
                      {Meta.label}
                    </button>
                  );
                })}
                <button
                  onClick={openTransit}
                  className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[11px] font-semibold text-foreground/70 transition hover:bg-muted"
                >
                  <Bus className="size-3.5" />
                  Jamoat transporti
                  <ExternalLink className="size-3 opacity-60" />
                </button>
              </div>
            )}

            {nav.phase === "error" && (
              <div className="border-t border-border/60 px-4 py-3">
                <button
                  onClick={() => startNavigation(nav.target)}
                  className="rounded-full bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground shadow-soft hover:shadow-glow"
                >
                  Qayta urinish
                </button>
              </div>
            )}

            {nav.phase === "active" && nav.route && !navCollapsed && (
              <div
                ref={stepListRef}
                className="max-h-52 overflow-y-auto border-t border-border/60 px-2 py-2"
              >
                {nav.route.steps.map((step, i) => {
                  const StepIcon = stepIcon(step);
                  const active = i === nav.activeStep;
                  return (
                    <div
                      key={i}
                      data-step={i}
                      className={`flex items-center gap-3 rounded-xl px-2.5 py-2 transition ${
                        active ? "bg-primary/10" : ""
                      }`}
                    >
                      <div
                        className={`flex size-7 shrink-0 items-center justify-center rounded-lg ${
                          active
                            ? "bg-primary text-primary-foreground"
                            : "bg-muted text-foreground/60"
                        }`}
                      >
                        <StepIcon className="size-3.5" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div
                          className={`truncate text-xs ${active ? "font-semibold text-foreground" : "text-foreground/75"}`}
                        >
                          {step.instruction}
                        </div>
                      </div>
                      <div className="shrink-0 text-[11px] text-muted-foreground">
                        {formatDistance(step.distanceMeters)}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
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
