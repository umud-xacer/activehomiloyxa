/**
 * The one map surface every part of the app uses -- category/subcategory listing maps, product
 * detail mini-maps, the global `/map` search page, and the full-screen "Marshrut" navigation
 * experience all render through this component. Built on the Yandex Maps JS API v2.1
 * (`@/lib/yandex-maps`'s `loadYandexMaps()`), which also backs `@/lib/routing` (multiRouter) and
 * `@/lib/geocoding` (Geocoder) -- one `VITE_YANDEX_MAPS_API_KEY` covers all three.
 *
 * When the key is unset (or the script fails to load), this renders a calm "Xarita sozlanmagan"
 * placeholder instead of crashing the page -- see `YandexMapsKeyMissingError`. This mirrors the
 * project's established stance on map-provider keys (see git history / CLAUDE.md): a missing or
 * misconfigured key is an expected, recoverable state during setup, never a hard crash.
 *
 * Clicking a marker navigates straight to its `href` (the listing's Product Detail page) -- there
 * is no more "start navigation from the map popup" shortcut. Navigation now starts from the
 * detail page's own "Marshrut" button, which sets the `navigateTarget` prop here to open the
 * full-screen turn-by-turn experience (mode switcher, live position tracking, mode-specific
 * marker) directly.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ClientOnly, useNavigate } from "@tanstack/react-router";
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
  Loader2,
  Map as MapIcon,
  Satellite,
  Globe2,
  Search,
  MapPin,
  Car,
  Footprints,
  Bus,
  AlertTriangle,
  type LucideIcon,
} from "lucide-react";
import {
  loadYandexMaps,
  getYandexMapsApiKey,
  YandexMapsKeyMissingError,
  type YMapsMap,
  type YMapsClusterer,
  type YMapsPlacemark,
  type YMapsPolygon,
  type YMapsCircle,
  type YMapsPolyline,
  type YMapsNamespace,
} from "@/lib/yandex-maps";
import {
  fetchRoute,
  formatDistance,
  formatDuration,
  distanceMeters,
  RoutingError,
  type RouteResult,
  type TravelMode,
} from "@/lib/routing";
import { searchPlaces, type GeocodeResult } from "@/lib/geocoding";

type StyleKey = "street" | "satellite" | "hybrid";

const YANDEX_MAP_TYPE: Record<StyleKey, string> = {
  street: "yandex#map",
  satellite: "yandex#satellite",
  hybrid: "yandex#hybrid",
};

const STYLE_META: Record<StyleKey, { label: string; Icon: LucideIcon }> = {
  street: { label: "Standart", Icon: MapIcon },
  satellite: { label: "Sun'iy yo'ldosh", Icon: Satellite },
  hybrid: { label: "Aralash", Icon: Globe2 },
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
  /** Product Detail page path -- clicking the marker navigates here directly. */
  href?: string;
  category?: string;
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
  activeStepIndex: number;
  error?: string;
  userPos?: { lat: number; lng: number; heading?: number | null };
}

const MODE_META: Record<TravelMode, { label: string; Icon: LucideIcon }> = {
  driving: { label: "Avtomobil", Icon: Car },
  walking: { label: "Piyoda", Icon: Footprints },
  transit: { label: "Jamoat transporti", Icon: Bus },
};

// Small hand-rolled inline glyphs for the live position "puck" -- kept intentionally simple
// (single filled path each) so the mode-specific marker doesn't depend on rendering a React
// icon tree into a raw HTML string, which Yandex's custom placemark layout requires.
const MODE_GLYPH: Record<TravelMode, string> = {
  driving:
    '<svg viewBox="0 0 24 24" width="10" height="10" fill="white"><path d="M5 11l1.5-4.5A2 2 0 0 1 8.4 5h7.2a2 2 0 0 1 1.9 1.5L19 11v6a1 1 0 0 1-1 1h-1a1 1 0 0 1-1-1v-1H8v1a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1v-6zm2.5.5h9l-1-3h-7l-1 3zM7 14a1 1 0 1 0 0-2 1 1 0 0 0 0 2zm10 0a1 1 0 1 0 0-2 1 1 0 0 0 0 2z"/></svg>',
  walking:
    '<svg viewBox="0 0 24 24" width="10" height="10" fill="white"><circle cx="13" cy="4" r="2"/><path d="M9 8.5 5 10l1 2.2 3-1.1v3.4L6 19l2 1 3.2-4.6L14 18l2 1 1-2-2.8-4.4L14 8h3V6h-4.5A3 3 0 0 0 9 8.5z"/></svg>',
  transit:
    '<svg viewBox="0 0 24 24" width="10" height="10" fill="white"><path d="M6 5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V5zm2 11a1 1 0 1 0 0 2 1 1 0 0 0 0-2zm8 0a1 1 0 1 0 0 2 1 1 0 0 0 0-2zM7 8h10V6H7v2zm0 4h10v-2H7v2z"/></svg>',
};

interface Props {
  markers: MapMarker[];
  center?: { lat: number; lng: number };
  zoom?: number;
  /** Set (to a new object) whenever the caller wants the map to jump to a point. */
  focus?: FocusTarget | null;
  height?: string;
  className?: string;
  onSelect?: (m: MapMarker) => void;
  onAreaSearch?: (area: AreaSearch) => void;
  onPlaceSearch?: (result: GeocodeResult) => void;
  showCountBadge?: boolean;
  enableDrawTools?: boolean;
  enableSearch?: boolean;
  filterOptions?: FilterOption[];
  activeFilterKeys?: string[];
  onFilterKeysChange?: (keys: string[]) => void;
  /** Set from a "Marshrut" button (Product Detail page) to open the full-screen turn-by-turn
   * navigation experience straight to this marker. Call `onNavigateHandled` once consumed so the
   * caller can clear the trigger and avoid re-opening on unrelated re-renders. */
  navigateTarget?: MapMarker | null;
  onNavigateHandled?: () => void;
}

function escapeHtml(s: string): string {
  return s.replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!,
  );
}

function pinHtml(marker: MapMarker, selected: boolean): string {
  const accentStyle =
    !selected && marker.accent
      ? ` style="background:${marker.accent};border-color:${marker.accent};color:#fff"`
      : "";
  return `<div class="ah-pin${selected ? " ah-pin--selected" : ""}"${accentStyle}>${escapeHtml(marker.label)}</div>`;
}

function bboxFromCorners(sw: [number, number], ne: [number, number]): BoundsBox {
  return { south: sw[0], west: sw[1], north: ne[0], east: ne[1] };
}

/** Deep-links to Yandex Maps' own panorama viewer for the point -- a normal outbound link, no
 * embed needed (Yandex's panorama coverage is queried by point, not by a separate API key). */
function streetViewUrl(lat: number, lng: number): string {
  return `https://yandex.com/maps/?panorama%5Bpoint%5D=${lng},${lat}&panorama%5Bdirection%5D=180,0&z=17`;
}

/** Outbound fallback if Yandex's in-app "masstransit" mode returns no route for this area (its
 * schedule/transfer coverage is strongest in Russia/CIS metro areas and may be thin elsewhere). */
function transitFallbackUrl(from: { lat: number; lng: number }, to: { lat: number; lng: number }) {
  return `https://yandex.com/maps/?rtext=${from.lat},${from.lng}~${to.lat},${to.lng}&rtt=mt`;
}

export function YandexMapView(props: Props) {
  return (
    <ClientOnly
      fallback={<MapSkeleton height={props.height ?? "70vh"} className={props.className} />}
    >
      <YandexMapViewClient {...props} />
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

function MapKeyMissing({ height, className = "" }: { height: string; className?: string }) {
  return (
    <div
      className={`relative flex items-center justify-center overflow-hidden rounded-3xl border border-dashed border-border bg-card/60 ${className}`}
      style={{ height }}
    >
      <div className="flex max-w-xs flex-col items-center gap-2 px-6 text-center">
        <AlertTriangle className="size-6 text-muted-foreground" />
        <div className="text-sm font-semibold text-foreground">Xarita sozlanmagan</div>
        <p className="text-xs text-muted-foreground">
          `VITE_YANDEX_MAPS_API_KEY` topilmadi. Kalitni `.env` fayliga qo'shgach, xarita avtomatik
          ishga tushadi.
        </p>
      </div>
    </div>
  );
}

function YandexMapViewClient({
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
  navigateTarget = null,
  onNavigateHandled,
}: Props) {
  const navigate = useNavigate();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const ymapsRef = useRef<YMapsNamespace | null>(null);
  const mapRef = useRef<YMapsMap | null>(null);
  const clustererRef = useRef<YMapsClusterer | null>(null);
  const markersByIdRef = useRef<Map<string, YMapsPlacemark>>(new Map());
  const overlaysRef = useRef<Array<YMapsPolygon | YMapsCircle>>([]);
  const routeLayersRef = useRef<{ casing: YMapsPolyline; line: YMapsPolyline } | null>(null);
  const puckRef = useRef<YMapsPlacemark | null>(null);
  const myLocationMarkerRef = useRef<YMapsPlacemark | null>(null);
  const searchMarkerRef = useRef<YMapsPlacemark | null>(null);
  const routeFittedRef = useRef<string | null>(null);
  const pinLayoutRef = useRef<unknown>(null);
  const clusterLayoutRef = useRef<unknown>(null);
  const puckLayoutRef = useRef<unknown>(null);
  const drawStateRef = useRef<{
    mode: "none" | "polygon" | "circle";
    points: [number, number][];
    tempLayer: YMapsPolygon | YMapsCircle | YMapsPolyline | null;
    circleCenter: [number, number] | null;
    dragging: boolean;
  }>({ mode: "none", points: [], tempLayer: null, circleCenter: null, dragging: false });

  const [mapReady, setMapReady] = useState(false);
  const [keyMissing, setKeyMissing] = useState(!getYandexMapsApiKey());
  const [loadFailed, setLoadFailed] = useState(false);

  const [style, setStyle] = useState<StyleKey>("street");
  const [layersOpen, setLayersOpen] = useState(false);
  const [drawMode, setDrawMode] = useState<"none" | "polygon" | "circle">("none");
  const [overlayCount, setOverlayCount] = useState(0);
  const [fullscreen, setFullscreen] = useState(false);
  const [nav, setNav] = useState<NavState | null>(null);
  const [navCollapsed, setNavCollapsed] = useState(false);
  const [geolocating, setGeolocating] = useState(false);
  const [geolocateError, setGeolocateError] = useState<string | null>(null);
  const stepListRef = useRef<HTMLDivElement | null>(null);

  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<GeocodeResult[]>([]);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);

  useEffect(() => {
    if (!geolocateError) return;
    const timer = setTimeout(() => setGeolocateError(null), 4000);
    return () => clearTimeout(timer);
  }, [geolocateError]);

  // Debounced Yandex Geocoder lookup -- fires ~350ms after the user stops typing.
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
      const ymapsNs = ymapsRef.current;
      setSearchQuery(result.label);
      setSearchOpen(false);
      if (map && ymapsNs) {
        if (result.boundingBox) {
          map.setBounds(
            [
              [result.boundingBox.south, result.boundingBox.west],
              [result.boundingBox.north, result.boundingBox.east],
            ],
            { checkZoomRange: true, duration: 400 },
          );
        } else {
          void map.setCenter([result.lat, result.lng], 14, { duration: 400 });
        }
        searchMarkerRef.current?.geometry.setCoordinates([result.lat, result.lng]);
        if (!searchMarkerRef.current) {
          searchMarkerRef.current = new ymapsNs.Placemark(
            [result.lat, result.lng],
            {},
            {
              iconLayout: "default#image",
              iconImageHref:
                "data:image/svg+xml;utf8," +
                encodeURIComponent(
                  '<svg xmlns="http://www.w3.org/2000/svg" width="30" height="30"><path d="M15 2c-6 0-11 4.6-11 11 0 8 11 15 11 15s11-7 11-15c0-6.4-5-11-11-11z" fill="#e5484d" stroke="white" stroke-width="2"/></svg>',
                ),
              iconImageSize: [30, 30],
              iconImageOffset: [-15, -30],
            },
          );
          map.geoObjects.add(searchMarkerRef.current);
        }
      }
      onPlaceSearch?.(result);
    },
    [onPlaceSearch],
  );

  // Init map once.
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    let cancelled = false;

    loadYandexMaps()
      .then((ymapsNs) => {
        if (cancelled || !containerRef.current || mapRef.current) return;
        ymapsRef.current = ymapsNs;

        pinLayoutRef.current = ymapsNs.templateLayoutFactory.createClass(
          '<div style="position:relative">$[properties.iconContent]</div>',
        );
        clusterLayoutRef.current = ymapsNs.templateLayoutFactory.createClass(
          '<div class="ah-cluster" style="width:42px;height:42px;position:relative;left:-21px;top:-21px">$[properties.geoObjects.length]</div>',
        );

        const map = new ymapsNs.Map(
          containerRef.current,
          { center: [center.lat, center.lng], zoom, type: YANDEX_MAP_TYPE.street, controls: [] },
          { suppressMapOpenBlock: true, yandexMapDisablePoiInteractivity: true },
        );
        map.controls.add("zoomControl", { position: { right: 12, bottom: 90 } });
        mapRef.current = map;

        const cluster = new ymapsNs.Clusterer({
          preset: "islands#invertedBlueClusterIcons",
          clusterIconLayout: clusterLayoutRef.current,
          clusterIconShape: { type: "Circle", coordinates: [0, 0], radius: 21 },
          groupByCoordinates: false,
          clusterDisableClickZoom: false,
          gridSize: 64,
        });
        map.geoObjects.add(cluster as unknown as never);
        clustererRef.current = cluster;
        setMapReady(true);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof YandexMapsKeyMissingError) {
          setKeyMissing(true);
        } else {
          setLoadFailed(true);
        }
      });

    return () => {
      cancelled = true;
      mapRef.current?.destroy();
      mapRef.current = null;
      clustererRef.current = null;
      markersByIdRef.current.clear();
      searchMarkerRef.current = null;
      myLocationMarkerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Style switching.
  useEffect(() => {
    mapRef.current?.setType(YANDEX_MAP_TYPE[style]);
  }, [style, mapReady]);

  const routeTo = useCallback(
    async (userPos: { lat: number; lng: number }, target: MapMarker, mode: TravelMode) => {
      setNav((n) => (n ? { ...n, phase: "routing", mode } : n));
      try {
        const route = await fetchRoute(userPos, { lat: target.lat, lng: target.lng }, mode);
        setNav((n) =>
          n && n.target.id === target.id ? { ...n, phase: "active", route, activeStepIndex: 0 } : n,
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
      setNav({ target, mode: "driving", phase: "locating", activeStepIndex: 0 });
      setFullscreen(true);
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

  // "Marshrut" trigger from a caller (e.g. Product Detail's route button).
  useEffect(() => {
    if (!navigateTarget) return;
    startNavigation(navigateTarget);
    onNavigateHandled?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [navigateTarget]);

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

  // Markers (clustered). Click navigates straight to the listing's Product Detail page.
  useEffect(() => {
    const cluster = clustererRef.current;
    const ymapsNs = ymapsRef.current;
    if (!cluster || !ymapsNs) return;

    cluster.removeAll();
    markersByIdRef.current.clear();

    const placemarks = markers.map((m) => {
      const placemark = new ymapsNs.Placemark(
        [m.lat, m.lng],
        { iconContent: pinHtml(m, false), hintContent: m.title },
        {
          iconLayout: pinLayoutRef.current,
          iconShape: {
            type: "Rectangle",
            coordinates: [
              [-45, -46],
              [45, 6],
            ],
          },
        },
      );
      placemark.events.add("click", () => {
        markersByIdRef.current.forEach((pm, id) => {
          const src = markers.find((mm) => mm.id === id);
          if (src) pm.properties.set("iconContent", pinHtml(src, id === m.id));
        });
        if (m.href) {
          navigate({ to: m.href });
        } else {
          onSelect?.(m);
        }
      });
      markersByIdRef.current.set(m.id, placemark);
      return placemark;
    });

    cluster.add(placemarks);

    return () => {
      cluster.removeAll();
      markersByIdRef.current.clear();
    };
  }, [markers, onSelect, navigate, mapReady]);

  // Focus -- flies to a specific point on demand (re-clustering naturally resolves the target
  // pin out of any cluster once zoomed in, so there's no separate "reveal from cluster" step).
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !focus) return;
    void map.setCenter([focus.lat, focus.lng], focus.zoom ?? Math.max(map.getZoom(), 14), {
      duration: 500,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus?.id, focus?.lat, focus?.lng, focus?.zoom, mapReady]);

  // Drawing tools -- hand-rolled on the map's own mouse events (mirrors the previous Leaflet
  // implementation; Yandex's map event names/coords shape are close enough to be a direct port).
  useEffect(() => {
    const map = mapRef.current;
    const ymapsNs = ymapsRef.current;
    if (!map || !ymapsNs) return;
    const state = drawStateRef.current;
    state.mode = drawMode;
    state.points = [];
    state.circleCenter = null;
    state.dragging = false;
    if (state.tempLayer) {
      map.geoObjects.remove(state.tempLayer as unknown as never);
      state.tempLayer = null;
    }
    if (drawMode === "none") {
      map.behaviors.enable("drag");
      return;
    }
    map.behaviors.disable("drag");

    const finishPolygon = () => {
      if (state.points.length >= 3) {
        const poly = new ymapsNs.Polygon(
          [state.points],
          {},
          {
            fillColor: "var(--primary)",
            fillOpacity: 0.15,
            strokeColor: "var(--primary)",
            strokeWidth: 2,
          },
        );
        map.geoObjects.add(poly as unknown as never);
        overlaysRef.current.push(poly);
        setOverlayCount(overlaysRef.current.length);
        const lats = state.points.map((p) => p[0]);
        const lngs = state.points.map((p) => p[1]);
        onAreaSearch?.({
          kind: "polygon",
          bbox: {
            south: Math.min(...lats),
            north: Math.max(...lats),
            west: Math.min(...lngs),
            east: Math.max(...lngs),
          },
        });
      }
      if (state.tempLayer) map.geoObjects.remove(state.tempLayer as unknown as never);
      state.tempLayer = null;
      state.points = [];
      setDrawMode("none");
    };

    const onClick = (e: { get<T>(key: string): T }) => {
      if (state.mode !== "polygon") return;
      const coords = e.get<[number, number]>("coords");
      state.points.push(coords);
      if (state.tempLayer) map.geoObjects.remove(state.tempLayer as unknown as never);
      state.tempLayer = new ymapsNs.Polyline(
        state.points,
        {},
        { strokeColor: "var(--primary)", strokeWidth: 2, strokeStyle: "shortdash" },
      );
      map.geoObjects.add(state.tempLayer as unknown as never);
    };
    const onDblClick = (e: { get<T>(key: string): T; preventDefault?: () => void }) => {
      if (state.mode !== "polygon") return;
      e.preventDefault?.();
      finishPolygon();
    };
    const onMouseDown = (e: { get<T>(key: string): T }) => {
      if (state.mode !== "circle") return;
      const coords = e.get<[number, number]>("coords");
      state.circleCenter = coords;
      state.dragging = true;
      state.tempLayer = new ymapsNs.Circle(
        [coords, 1],
        {},
        {
          fillColor: "var(--primary)",
          fillOpacity: 0.12,
          strokeColor: "var(--primary)",
          strokeWidth: 2,
        },
      );
      map.geoObjects.add(state.tempLayer as unknown as never);
    };
    const onMouseMove = (e: { get<T>(key: string): T }) => {
      if (state.mode !== "circle" || !state.dragging || !state.circleCenter) return;
      const coords = e.get<[number, number]>("coords");
      const radius = distanceMeters(
        { lat: state.circleCenter[0], lng: state.circleCenter[1] },
        { lat: coords[0], lng: coords[1] },
      );
      (state.tempLayer as YMapsCircle | null)?.geometry.setRadius(radius);
    };
    const onMouseUp = () => {
      if (state.mode !== "circle" || !state.dragging || !state.circleCenter) return;
      state.dragging = false;
      const circle = state.tempLayer as YMapsCircle | null;
      state.tempLayer = null;
      const radius = circle?.geometry.getRadius() ?? 0;
      if (circle && radius > 20) {
        overlaysRef.current.push(circle);
        setOverlayCount(overlaysRef.current.length);
        const [lat, lng] = state.circleCenter;
        onAreaSearch?.({
          kind: "circle",
          bbox: {
            south: lat - radius / 111320,
            north: lat + radius / 111320,
            west: lng - radius / (111320 * Math.cos((lat * Math.PI) / 180)),
            east: lng + radius / (111320 * Math.cos((lat * Math.PI) / 180)),
          },
          center: { lat, lng },
          radiusMeters: radius,
        });
      } else if (circle) {
        map.geoObjects.remove(circle as unknown as never);
      }
      setDrawMode("none");
    };

    map.events.add("click", onClick);
    map.events.add("dblclick", onDblClick);
    map.events.add("mousedown", onMouseDown);
    map.events.add("mousemove", onMouseMove);
    map.events.add("mouseup", onMouseUp);

    return () => {
      map.events.remove("click", onClick);
      map.events.remove("dblclick", onDblClick);
      map.events.remove("mousedown", onMouseDown);
      map.events.remove("mousemove", onMouseMove);
      map.events.remove("mouseup", onMouseUp);
      map.behaviors.enable("drag");
    };
  }, [drawMode, onAreaSearch, mapReady]);

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
          let activeStepIndex = n.activeStepIndex;
          const nextStep = n.route?.steps[activeStepIndex + 1];
          if (nextStep && distanceMeters(p, nextStep.location) < 40) activeStepIndex += 1;
          return { ...n, userPos: p, activeStepIndex };
        });
      },
      (err) => console.warn("[nav watch]", err.message),
      { enableHighAccuracy: true, maximumAge: 2000, timeout: 15000 },
    );
    return () => navigator.geolocation.clearWatch(id);
  }, [navTargetId]);

  // Route polyline (casing + colored line) + one-time bounds fit when a route first arrives.
  useEffect(() => {
    const map = mapRef.current;
    const ymapsNs = ymapsRef.current;
    if (!map || !ymapsNs) return;
    if (routeLayersRef.current) {
      map.geoObjects.remove(routeLayersRef.current.casing as unknown as never);
      map.geoObjects.remove(routeLayersRef.current.line as unknown as never);
      routeLayersRef.current = null;
    }

    if (!nav?.route) return;
    const coords = nav.route.coordinates.map((c) => [c.lat, c.lng] as [number, number]);
    const casing = new ymapsNs.Polyline(
      coords,
      {},
      { strokeColor: "#0b0e2bAA", strokeWidth: 8, strokeLineCap: "round" },
    );
    const line = new ymapsNs.Polyline(
      coords,
      {},
      { strokeColor: "var(--primary)", strokeWidth: 5, strokeLineCap: "round" },
    );
    map.geoObjects.add(casing as unknown as never);
    map.geoObjects.add(line as unknown as never);
    routeLayersRef.current = { casing, line };

    const fitKey = `${nav.target.id}:${nav.mode}`;
    if (routeFittedRef.current !== fitKey && coords.length > 0) {
      const lats = coords.map((c) => c[0]);
      const lngs = coords.map((c) => c[1]);
      void map.setBounds(
        [
          [Math.min(...lats), Math.min(...lngs)],
          [Math.max(...lats), Math.max(...lngs)],
        ],
        { checkZoomRange: true, zoomMargin: 64, duration: 500 },
      );
      routeFittedRef.current = fitKey;
    }

    return () => {
      map.geoObjects.remove(casing as unknown as never);
      map.geoObjects.remove(line as unknown as never);
    };
  }, [nav?.route, nav?.target.id, nav?.mode]);

  // Live location puck -- glyph matches the currently selected travel mode.
  useEffect(() => {
    const map = mapRef.current;
    const ymapsNs = ymapsRef.current;
    if (!map || !ymapsNs || !nav?.userPos) {
      if (puckRef.current) map?.geoObjects.remove(puckRef.current as unknown as never);
      puckRef.current = null;
      return;
    }
    const { lat, lng } = nav.userPos;
    if (!puckLayoutRef.current) {
      puckLayoutRef.current = ymapsNs.templateLayoutFactory.createClass(
        '<div class="ah-puck" style="position:relative;left:-9px;top:-9px">' +
          '<span class="ah-puck__ring"></span>' +
          '<span class="ah-puck__dot" style="display:flex;align-items:center;justify-content:center">$[properties.glyph]</span>' +
          "</div>",
      );
    }
    if (puckRef.current) {
      puckRef.current.geometry.setCoordinates([lat, lng]);
      puckRef.current.properties.set("glyph", MODE_GLYPH[nav.mode]);
    } else {
      puckRef.current = new ymapsNs.Placemark(
        [lat, lng],
        { glyph: MODE_GLYPH[nav.mode] },
        {
          iconLayout: puckLayoutRef.current,
          iconShape: { type: "Circle", coordinates: [0, 0], radius: 9 },
        },
      );
      map.geoObjects.add(puckRef.current as unknown as never);
    }
  }, [nav?.userPos, nav?.mode]);

  // Auto-scroll the step list to keep the active step in view.
  useEffect(() => {
    if (!nav || nav.phase !== "active") return;
    const container = stepListRef.current;
    const activeEl = container?.querySelector<HTMLElement>(`[data-step="${nav.activeStepIndex}"]`);
    activeEl?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [nav?.activeStepIndex, nav?.phase]);

  const recenterOnUser = () => {
    if (!nav?.userPos || !mapRef.current) return;
    void mapRef.current.setCenter([nav.userPos.lat, nav.userPos.lng], 17, { duration: 400 });
  };

  const clearOverlays = () => {
    const map = mapRef.current;
    overlaysRef.current.forEach((o) => map?.geoObjects.remove(o as unknown as never));
    overlaysRef.current = [];
    setOverlayCount(0);
  };

  const geolocate = () => {
    setGeolocateError(null);
    const map = mapRef.current;
    const ymapsNs = ymapsRef.current;
    if (!navigator.geolocation || !map || !ymapsNs) {
      setGeolocateError("Brauzeringiz joylashuvni aniqlay olmaydi.");
      return;
    }
    setGeolocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setGeolocating(false);
        const { latitude, longitude } = pos.coords;
        void map.setCenter([latitude, longitude], 15, { duration: 500 });
        if (!puckLayoutRef.current) {
          puckLayoutRef.current = ymapsNs.templateLayoutFactory.createClass(
            '<div class="ah-puck" style="position:relative;left:-9px;top:-9px">' +
              '<span class="ah-puck__ring"></span><span class="ah-puck__dot"></span></div>',
          );
        }
        if (myLocationMarkerRef.current) {
          myLocationMarkerRef.current.geometry.setCoordinates([latitude, longitude]);
        } else {
          myLocationMarkerRef.current = new ymapsNs.Placemark(
            [latitude, longitude],
            {},
            {
              iconLayout: puckLayoutRef.current,
              iconShape: { type: "Circle", coordinates: [0, 0], radius: 9 },
            },
          );
          map.geoObjects.add(myLocationMarkerRef.current as unknown as never);
        }
      },
      (err) => {
        setGeolocating(false);
        setGeolocateError(
          err.code === err.PERMISSION_DENIED
            ? "Joylashuvga ruxsat berilmadi."
            : "Joylashuvni aniqlab bo'lmadi.",
        );
        console.warn("[geolocation]", err.message);
      },
      { enableHighAccuracy: true, timeout: 8000 },
    );
  };

  const openStreetView = () => {
    const map = mapRef.current;
    const c = map ? map.getCenter() : [center.lat, center.lng];
    window.open(streetViewUrl(c[0], c[1]), "_blank", "noopener,noreferrer");
  };

  const containerStyle = useMemo(
    () => ({ height: fullscreen ? "100vh" : height }),
    [height, fullscreen],
  );

  if (keyMissing) return <MapKeyMissing height={height} className={className} />;
  if (loadFailed) {
    return (
      <div
        className={`relative flex items-center justify-center overflow-hidden rounded-3xl border border-border bg-card ${className}`}
        style={{ height }}
      >
        <p className="max-w-xs px-6 text-center text-xs text-muted-foreground">
          Xaritani yuklab bo'lmadi. Internet aloqasini tekshirib, sahifani yangilang.
        </p>
      </div>
    );
  }

  return (
    <div
      className={`relative transition-[border-radius] ${fullscreen ? "fixed inset-0 z-[999]" : className}`}
      style={containerStyle}
    >
      <div
        className={`absolute inset-0 overflow-hidden border border-border bg-card shadow-elevated ${
          fullscreen ? "rounded-none" : "rounded-3xl"
        }`}
      >
        <div ref={containerRef} className="absolute inset-0" />
      </div>

      <div className="absolute inset-x-0 top-0 z-[500] flex items-start justify-between gap-2 p-3 sm:p-4">
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

        <div className="flex shrink-0 flex-col gap-2">
          <ToolButton
            onClick={() => setFullscreen((v) => !v)}
            label={fullscreen ? "Kichraytirish" : "To'liq ekran"}
            icon={fullscreen ? <Minimize2 className="size-4" /> : <Maximize2 className="size-4" />}
          />
          <div className="relative">
            <ToolButton
              onClick={geolocate}
              label="Mening joylashuvim"
              icon={
                geolocating ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <LocateFixed className="size-4" />
                )
              }
            />
            {geolocateError && (
              <div className="glass absolute right-full top-1/2 mr-2 w-max max-w-[200px] -translate-y-1/2 rounded-xl px-3 py-2 text-[11px] font-medium text-destructive shadow-soft">
                {geolocateError}
              </div>
            )}
          </div>
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

      {showCountBadge && !nav && (
        <div className="glass absolute bottom-4 left-4 z-[500] rounded-2xl px-3 py-2 text-xs text-foreground/85 shadow-soft">
          <span className="font-semibold text-foreground">{markers.length.toLocaleString()}</span>{" "}
          xaritadagi natija
        </div>
      )}

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
              </div>
            )}

            {nav.phase === "error" && (
              <div className="flex flex-wrap items-center gap-2 border-t border-border/60 px-4 py-3">
                <button
                  onClick={() => startNavigation(nav.target)}
                  className="rounded-full bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground shadow-soft hover:shadow-glow"
                >
                  Qayta urinish
                </button>
                {nav.mode === "transit" && nav.userPos && (
                  <a
                    href={transitFallbackUrl(nav.userPos, {
                      lat: nav.target.lat,
                      lng: nav.target.lng,
                    })}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-2 text-xs font-semibold text-foreground/70 transition hover:bg-muted"
                  >
                    Yandex Maps'da ochish <ExternalLink className="size-3" />
                  </a>
                )}
              </div>
            )}

            {nav.phase === "active" && nav.route && !navCollapsed && (
              <div
                ref={stepListRef}
                className="max-h-52 overflow-y-auto border-t border-border/60 px-2 py-2"
              >
                {nav.route.steps.map((step, i) => {
                  const active = i === nav.activeStepIndex;
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
                        <Navigation className="size-3.5" />
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
