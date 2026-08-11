/**
 * Yandex Maps JavaScript API v2.1 loader -- the single script tag every map surface in the app
 * depends on (`YandexMapView`, `routing.ts`'s multiRouter-based `fetchRoute`, `geocoding.ts`'s
 * Geocoder-based `searchPlaces`). One `VITE_YANDEX_MAPS_API_KEY` covers all three surfaces
 * (map tiles, Geocoder, multiRouter) -- Yandex bundles them under a single "JavaScript API and
 * HTTP Geocoder" key (https://developer.tech.yandex.ru/services), free tier.
 *
 * Promise-cached so every caller shares one script load/one `ymaps.ready()` regardless of how
 * many map components mount concurrently (category page + product-detail mini-map, for example).
 *
 * No `@types/yandex-maps` dependency yet -- the `ymaps` global is typed loosely below, just
 * enough surface for this app's usage (Map/Placemark/Clusterer/geocode/multiRouter/events).
 */

export interface YMapsGeoObjectCollection {
  add(obj: unknown): void;
  remove(obj: unknown): void;
  removeAll(): void;
}

export interface YMapsEventManager {
  add(event: string, handler: (e: YMapsEvent) => void): void;
  remove(event: string, handler: (e: YMapsEvent) => void): void;
}

export interface YMapsEvent {
  get<T = unknown>(key: string): T;
  originalEvent?: { domEvent?: { button?: number } };
}

export interface YMapsMap {
  geoObjects: YMapsGeoObjectCollection;
  events: YMapsEventManager;
  behaviors: { enable(name: string): void; disable(name: string): void };
  controls: { add(name: string, opts?: Record<string, unknown>): void; remove(name: string): void };
  setCenter(coords: [number, number], zoom?: number, opts?: { duration?: number }): Promise<void>;
  setZoom(zoom: number, opts?: { duration?: number }): Promise<void>;
  setBounds(
    bounds: [[number, number], [number, number]],
    opts?: { checkZoomRange?: boolean; zoomMargin?: number | number[]; duration?: number },
  ): Promise<void>;
  setType(type: string): void;
  getCenter(): [number, number];
  getZoom(): number;
  getBounds(): [[number, number], [number, number]];
  destroy(): void;
  container: { fitToViewport(): void };
}

export interface YMapsPlacemark {
  events: YMapsEventManager;
  geometry: { setCoordinates(coords: [number, number]): void; getCoordinates(): [number, number] };
  properties: { set(key: string, value: unknown): void };
  options: { set(key: string, value: unknown): void };
}

export interface YMapsClusterer {
  add(obj: unknown | unknown[]): void;
  removeAll(): void;
  events: YMapsEventManager;
  options: { set(key: string, value: unknown): void };
}

export interface YMapsPolygon {
  geometry: { setCoordinates(coords: [number, number][][]): void };
}

export interface YMapsCircle {
  geometry: {
    getRadius(): number;
    setRadius(radius: number): void;
    getCoordinates(): [number, number];
  };
}

export interface YMapsPolyline {
  geometry: { setCoordinates(coords: [number, number][]): void };
}

export interface YMapsGeocodeResultItem {
  getAddressLine(): string;
  geometry: { getCoordinates(): [number, number] };
  properties: { get(key: string): unknown };
}

export interface YMapsGeocodeResult {
  geoObjects: {
    get(index: number): YMapsGeocodeResultItem | undefined;
    getLength(): number;
  };
}

export type YMapsMultiRouteMode = "auto" | "pedestrian" | "masstransit";

export interface YMapsMultiRoute {
  events: YMapsEventManager;
  getActiveRoute(): YMapsMultiRouteActiveRoute | null;
  getRoutes(): { get(i: number): YMapsMultiRouteActiveRoute } | null;
  model: {
    events: YMapsEventManager;
    getRoutes(): unknown;
  };
}

export interface YMapsMultiRouteActiveRoute {
  properties: { get(key: string): unknown };
  geometry: { getCoordinates(): [number, number][] };
  getPaths(): { each(cb: (path: YMapsMultiRoutePath) => void): void };
}

export interface YMapsMultiRoutePath {
  properties: { get(key: string): unknown };
  getSegments(): { each(cb: (segment: YMapsMultiRouteSegment) => void): void };
}

export interface YMapsMultiRouteSegment {
  properties: { get(key: string): unknown };
  getCoordinates?: () => [number, number][];
}

export interface YMapsNamespace {
  Map: new (
    container: HTMLElement,
    state: {
      center: [number, number];
      zoom: number;
      type?: string;
      controls?: string[];
    },
    opts?: Record<string, unknown>,
  ) => YMapsMap;
  Placemark: new (
    coords: [number, number],
    properties?: Record<string, unknown>,
    options?: Record<string, unknown>,
  ) => YMapsPlacemark;
  Clusterer: new (opts?: Record<string, unknown>) => YMapsClusterer;
  Polygon: new (
    coords: [number, number][][],
    properties?: Record<string, unknown>,
    options?: Record<string, unknown>,
  ) => YMapsPolygon;
  Circle: new (
    geometry: [[number, number], number],
    properties?: Record<string, unknown>,
    options?: Record<string, unknown>,
  ) => YMapsCircle;
  Polyline: new (
    coords: [number, number][],
    properties?: Record<string, unknown>,
    options?: Record<string, unknown>,
  ) => YMapsPolyline;
  templateLayoutFactory: {
    createClass(template: string, methods?: Record<string, unknown>): unknown;
  };
  multiRouter: {
    MultiRoute: new (
      params: {
        referencePoints: Array<[number, number] | string>;
        params?: { routingMode?: YMapsMultiRouteMode; results?: number };
      },
      options?: Record<string, unknown>,
    ) => YMapsMultiRoute;
  };
  geocode(
    request: string | [number, number],
    options?: { results?: number; kind?: string; boundedBy?: unknown },
  ): Promise<YMapsGeocodeResult>;
  ready(cb?: () => void): Promise<void>;
  geoQuery?: unknown;
}

declare global {
  interface Window {
    ymaps?: YMapsNamespace;
  }
}

const SCRIPT_ID = "yandex-maps-jsapi";

export class YandexMapsKeyMissingError extends Error {
  constructor() {
    super("VITE_YANDEX_MAPS_API_KEY is not set");
    this.name = "YandexMapsKeyMissingError";
  }
}

export class YandexMapsLoadError extends Error {
  constructor() {
    super("Failed to load the Yandex Maps script");
    this.name = "YandexMapsLoadError";
  }
}

export function getYandexMapsApiKey(): string | null {
  const key = import.meta.env.VITE_YANDEX_MAPS_API_KEY as string | undefined;
  return key && key.trim().length > 0 ? key.trim() : null;
}

let loadPromise: Promise<YMapsNamespace> | null = null;

/** Injects (once) the Yandex Maps JS API script and resolves with the ready `ymaps` namespace.
 * Promise-cached across every caller/mount. Rejects with `YandexMapsKeyMissingError` when
 * `VITE_YANDEX_MAPS_API_KEY` is unset -- callers should catch this specifically to render a
 * "xarita sozlanmagan" placeholder instead of a crash (see `YandexMapView`'s doc comment for why
 * this app treats missing map-provider keys as an expected, recoverable state, not a bug). */
export function loadYandexMaps(): Promise<YMapsNamespace> {
  if (loadPromise) return loadPromise;

  const apiKey = getYandexMapsApiKey();
  if (!apiKey) {
    return Promise.reject(new YandexMapsKeyMissingError());
  }

  loadPromise = new Promise<YMapsNamespace>((resolve, reject) => {
    if (window.ymaps) {
      window.ymaps.ready(() => resolve(window.ymaps!));
      return;
    }
    const existing = document.getElementById(SCRIPT_ID) as HTMLScriptElement | null;
    const script = existing ?? document.createElement("script");
    script.id = SCRIPT_ID;
    script.src = `https://api-maps.yandex.ru/2.1/?apikey=${encodeURIComponent(apiKey)}&lang=ru_RU`;
    script.async = true;
    script.onload = () => {
      if (!window.ymaps) {
        reject(new YandexMapsLoadError());
        return;
      }
      window.ymaps.ready(() => resolve(window.ymaps!));
    };
    script.onerror = () => reject(new YandexMapsLoadError());
    if (!existing) document.head.appendChild(script);
  }).catch((err) => {
    loadPromise = null; // allow retry on transient network failure
    throw err;
  });

  return loadPromise;
}
