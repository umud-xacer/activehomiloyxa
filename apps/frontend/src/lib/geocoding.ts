/**
 * Place/address search -- tries the Yandex Geocoder first (same JS API key/script as the map
 * itself and `routing.ts`'s multiRouter, see `@/lib/yandex-maps`'s doc comment), and transparently
 * falls back to OpenStreetMap's free, keyless Nominatim service whenever the Yandex call fails
 * (script load issue, key not authorized for the Geocoder product -- a separate product from the
 * Maps-JS-display one in Yandex's console, see [[yandex-geocoder-broken-2026-08-20]] -- or the key
 * missing entirely). This keeps place search working end-to-end regardless of that key's current
 * authorization state; if/when the Yandex Geocoder product is enabled, its results are used as-is
 * (no behavior change), Nominatim only ever fires as a fallback path.
 */
import {
  loadYandexMaps,
  YandexMapsKeyMissingError,
  type YMapsGeocodeResultItem,
} from "@/lib/yandex-maps";

export interface GeocodeResult {
  id: string;
  label: string;
  secondary?: string;
  lat: number;
  lng: number;
  kind: string;
  boundingBox?: { south: number; north: number; west: number; east: number };
}

function toGeocodeResult(obj: YMapsGeocodeResultItem): GeocodeResult {
  const [lat, lng] = obj.geometry.getCoordinates();
  const fullAddress = obj.getAddressLine();
  const name = (obj.properties.get("name") as string | undefined) || fullAddress;
  const secondary =
    fullAddress && fullAddress !== name
      ? fullAddress.startsWith(name)
        ? fullAddress.slice(name.length).replace(/^,\s*/, "")
        : fullAddress
      : undefined;
  const kind = (obj.properties.get("kind") as string | undefined) || "unknown";
  const bounded = obj.properties.get("boundedBy") as
    [[number, number], [number, number]] | undefined;

  return {
    id: `${lat.toFixed(6)},${lng.toFixed(6)}`,
    label: name,
    secondary: secondary || undefined,
    lat,
    lng,
    kind,
    boundingBox: bounded
      ? { south: bounded[0][0], west: bounded[0][1], north: bounded[1][0], east: bounded[1][1] }
      : undefined,
  };
}

interface NominatimHit {
  place_id: number;
  display_name: string;
  lat: string;
  lon: string;
  type: string;
  class: string;
  boundingbox: [string, string, string, string];
}

function toGeocodeResultFromNominatim(h: NominatimHit): GeocodeResult {
  const [south, north, west, east] = h.boundingbox.map(Number);
  const parts = h.display_name.split(",").map((p) => p.trim());
  return {
    id: String(h.place_id),
    label: parts[0] || h.display_name,
    secondary: parts.slice(1, 4).join(", ") || undefined,
    lat: Number(h.lat),
    lng: Number(h.lon),
    kind: h.type || h.class,
    boundingBox: { south, north, west, east },
  };
}

async function searchPlacesNominatim(query: string, limit: number): Promise<GeocodeResult[]> {
  const url =
    `https://nominatim.openstreetmap.org/search?format=jsonv2&addressdetails=0&limit=${limit}` +
    `&q=${encodeURIComponent(query)}`;
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`Nominatim search failed: HTTP ${res.status}`);
  const hits: NominatimHit[] = await res.json();
  return hits.map(toGeocodeResultFromNominatim);
}

async function reverseGeocodeNominatim(point: {
  lat: number;
  lng: number;
}): Promise<GeocodeResult | null> {
  const url = `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${point.lat}&lon=${point.lng}`;
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`Nominatim reverse failed: HTTP ${res.status}`);
  const hit: NominatimHit | { error?: string } = await res.json();
  if (!("place_id" in hit)) return null;
  return toGeocodeResultFromNominatim(hit);
}

// Yandex's `ymaps.geocode()` returns a plain Promise with no built-in cancellation -- track the
// latest request so a slow, stale response never clobbers a newer, faster one.
let latestRequestId = 0;

// Thrown when neither geocoder could answer the request (both the Yandex call and the Nominatim
// fallback failed) -- distinct from "the query legitimately had zero matches", which resolves
// with an empty array instead.
export class GeocodeUnavailableError extends Error {
  constructor(cause: unknown) {
    super("Geocoder request failed");
    this.name = "GeocodeUnavailableError";
    this.cause = cause;
  }
}

export async function searchPlaces(query: string, limit = 6): Promise<GeocodeResult[]> {
  const q = query.trim();
  if (q.length < 2) return [];

  const requestId = ++latestRequestId;
  let yandexErr: unknown;

  try {
    const ymaps = await loadYandexMaps();
    if (requestId !== latestRequestId) return [];
    const result = await ymaps.geocode(q, { results: limit });
    if (requestId !== latestRequestId) return [];
    const hits: GeocodeResult[] = [];
    const length = result.geoObjects.getLength();
    for (let i = 0; i < length; i += 1) {
      const obj = result.geoObjects.get(i);
      if (obj) hits.push(toGeocodeResult(obj));
    }
    return hits;
  } catch (err) {
    if (err instanceof YandexMapsKeyMissingError) {
      // Not configured at all -- go straight to the fallback, no point logging this one.
    } else {
      console.warn("[geocoding] Yandex search failed, falling back to Nominatim", err);
    }
    yandexErr = err;
  }

  try {
    const hits = await searchPlacesNominatim(q, limit);
    if (requestId !== latestRequestId) return [];
    return hits;
  } catch (err) {
    throw new GeocodeUnavailableError(err ?? yandexErr);
  }
}

/** Reverse geocoding -- resolves a coordinate to a human-readable address. Used by the
 * click-to-pin location flows (listing creation, "destination" confirmation before navigation). */
export async function reverseGeocode(point: {
  lat: number;
  lng: number;
}): Promise<GeocodeResult | null> {
  try {
    const ymaps = await loadYandexMaps();
    const result = await ymaps.geocode([point.lat, point.lng], { results: 1 });
    const obj = result.geoObjects.get(0);
    if (obj) return toGeocodeResult(obj);
  } catch (err) {
    if (!(err instanceof YandexMapsKeyMissingError)) {
      console.warn("[geocoding] Yandex reverse geocode failed, falling back to Nominatim", err);
    }
  }

  try {
    return await reverseGeocodeNominatim(point);
  } catch {
    return null;
  }
}
