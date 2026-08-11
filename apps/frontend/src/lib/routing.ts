/**
 * Turn-by-turn directions via Yandex's `multiRouter` (part of the same JS API key as the map
 * itself and the Geocoder -- see `@/lib/yandex-maps`'s doc comment). Replaces the previous
 * OSRM-based implementation now that every map surface in the app is Yandex-based; adds a real
 * "masstransit" (public transport) mode, which OSRM's public demo router never had.
 *
 * Known limitation: Yandex's JS API only localizes its own step instruction text into
 * `ru_RU`/`en_US`/`uk_UA`/`tr_TR` -- there is no `uz_UZ` output, unlike the old OSRM
 * implementation, which hand-built Uzbek instructions from OSRM's structured maneuver codes.
 * Yandex's `multiRouter` segments don't expose an equivalent structured maneuver type/modifier,
 * only pre-rendered text -- so step instructions here come through as Yandex gives them (`ru_RU`,
 * see the `lang` param on the script tag in `yandex-maps.ts`) rather than Uzbek. Distance/duration
 * formatting and the surrounding UI chrome stay Uzbek (`formatDistance`/`formatDuration` below).
 */
import {
  loadYandexMaps,
  type YMapsMultiRouteActiveRoute,
  type YMapsMultiRouteMode,
} from "@/lib/yandex-maps";

export interface RouteStep {
  instruction: string;
  distanceMeters: number;
  durationSeconds: number;
  maneuverType: string;
  maneuverModifier?: string;
  location: { lat: number; lng: number };
}

export interface RouteResult {
  coordinates: { lat: number; lng: number }[];
  distanceMeters: number;
  durationSeconds: number;
  steps: RouteStep[];
}

export class RoutingError extends Error {}

export type TravelMode = "driving" | "walking" | "transit";

const ROUTING_MODE: Record<TravelMode, YMapsMultiRouteMode> = {
  driving: "auto",
  walking: "pedestrian",
  transit: "masstransit",
};

/** Yandex's `MultiRoute` model starts its request as soon as it's constructed (it does not need
 * to be added to a map to resolve) -- this wraps that event-based model in a Promise so callers
 * can `await` a single result the same way the old OSRM `fetch()` call worked. */
function requestMultiRoute(
  ymapsNs: Awaited<ReturnType<typeof loadYandexMaps>>,
  from: { lat: number; lng: number },
  to: { lat: number; lng: number },
  mode: TravelMode,
): Promise<YMapsMultiRouteActiveRoute> {
  return new Promise((resolve, reject) => {
    let settled = false;
    const multiRoute = new ymapsNs.multiRouter.MultiRoute(
      {
        referencePoints: [
          [from.lat, from.lng],
          [to.lat, to.lng],
        ],
        params: { routingMode: ROUTING_MODE[mode], results: 1 },
      },
      { boundsAutoApply: false },
    );

    const timeout = window.setTimeout(() => {
      if (settled) return;
      settled = true;
      reject(new RoutingError("Marshrutni hisoblash vaqti tugadi. Qayta urinib ko'ring."));
    }, 12000);

    multiRoute.model.events.add("requestsuccess", () => {
      if (settled) return;
      const active = multiRoute.getActiveRoute();
      settled = true;
      window.clearTimeout(timeout);
      if (!active) {
        reject(new RoutingError("Bu ikki nuqta orasida yo'l topilmadi."));
        return;
      }
      resolve(active);
    });
    multiRoute.model.events.add("requestfail", () => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timeout);
      reject(
        new RoutingError("Marshrutni hisoblab bo'lmadi. Birozdan so'ng qayta urinib ko'ring."),
      );
    });
  });
}

function readNumberProp(props: { get(key: string): unknown }, key: string): number {
  const raw = props.get(key) as { value?: number } | number | undefined;
  if (typeof raw === "number") return raw;
  if (raw && typeof raw.value === "number") return raw.value;
  return 0;
}

function extractSteps(active: YMapsMultiRouteActiveRoute): RouteStep[] {
  const steps: RouteStep[] = [];
  try {
    active.getPaths().each((path) => {
      path.getSegments().each((segment) => {
        const text = (segment.properties.get("text") as string | undefined) ?? "Davom eting";
        const coords = segment.getCoordinates?.() ?? [];
        const last = coords[coords.length - 1];
        steps.push({
          instruction: text,
          distanceMeters: readNumberProp(segment.properties, "distance"),
          durationSeconds: readNumberProp(segment.properties, "duration"),
          maneuverType: "continue",
          location: last ? { lat: last[0], lng: last[1] } : { lat: 0, lng: 0 },
        });
      });
    });
  } catch {
    // Yandex's segment shape is only loosely typed here (no official @types package yet) --
    // if a field is missing/renamed in a future API revision, fall back to an empty step list
    // rather than crash the whole route (distance/duration/polyline still render fine without it).
  }
  return steps;
}

/** Fetches a route between two points for the given travel mode. Throws `RoutingError` with a
 * user-facing (Uzbek) message on failure -- callers should catch and show it inline rather than
 * crash the map. */
export async function fetchRoute(
  from: { lat: number; lng: number },
  to: { lat: number; lng: number },
  mode: TravelMode = "driving",
): Promise<RouteResult> {
  let ymapsNs;
  try {
    ymapsNs = await loadYandexMaps();
  } catch {
    throw new RoutingError("Xarita xizmatiga ulanib bo'lmadi. Internet aloqasini tekshiring.");
  }

  const active = await requestMultiRoute(ymapsNs, from, to, mode);

  const coordinates = active.geometry.getCoordinates().map(([lat, lng]) => ({ lat, lng }));

  return {
    coordinates,
    distanceMeters: readNumberProp(active.properties, "distance"),
    durationSeconds: readNumberProp(active.properties, "duration"),
    steps: extractSteps(active),
  };
}

export function formatDistance(meters: number): string {
  if (meters < 1000) return `${Math.round(meters / 10) * 10} m`;
  return `${(meters / 1000).toLocaleString(undefined, { maximumFractionDigits: 1 })} km`;
}

export function formatDuration(seconds: number): string {
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} daq`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest > 0 ? `${hours} soat ${rest} daq` : `${hours} soat`;
}

/** Haversine distance in meters -- used to advance the active turn-by-turn step as the user's
 * live position approaches each maneuver point. */
export function distanceMeters(
  a: { lat: number; lng: number },
  b: { lat: number; lng: number },
): number {
  const R = 6371000;
  const dLat = ((b.lat - a.lat) * Math.PI) / 180;
  const dLng = ((b.lng - a.lng) * Math.PI) / 180;
  const lat1 = (a.lat * Math.PI) / 180;
  const lat2 = (b.lat * Math.PI) / 180;
  const h = Math.sin(dLat / 2) ** 2 + Math.sin(dLng / 2) ** 2 * Math.cos(lat1) * Math.cos(lat2);
  return 2 * R * Math.asin(Math.sqrt(h));
}
