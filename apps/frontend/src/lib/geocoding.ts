/**
 * Place/address search via the Yandex Geocoder -- part of the same JS API key/script as the map
 * itself and `routing.ts`'s multiRouter (see `@/lib/yandex-maps`'s doc comment). Replaces the
 * previous Nominatim-based implementation now that every map surface in the app is Yandex-based.
 */
import { loadYandexMaps, type YMapsGeocodeResultItem } from "@/lib/yandex-maps";

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

// Yandex's `ymaps.geocode()` returns a plain Promise with no built-in cancellation -- track the
// latest request so a slow, stale response never clobbers a newer, faster one (same guarantee the
// old Nominatim/AbortController implementation gave callers who fire this on every keystroke).
let latestRequestId = 0;

export async function searchPlaces(query: string, limit = 6): Promise<GeocodeResult[]> {
  const q = query.trim();
  if (q.length < 2) return [];

  const requestId = ++latestRequestId;

  let ymaps;
  try {
    ymaps = await loadYandexMaps();
  } catch {
    return [];
  }
  if (requestId !== latestRequestId) return [];

  let result;
  try {
    result = await ymaps.geocode(q, { results: limit });
  } catch {
    return [];
  }
  if (requestId !== latestRequestId) return [];

  const hits: GeocodeResult[] = [];
  const length = result.geoObjects.getLength();
  for (let i = 0; i < length; i += 1) {
    const obj = result.geoObjects.get(i);
    if (obj) hits.push(toGeocodeResult(obj));
  }
  return hits;
}

/** Reverse geocoding -- resolves a coordinate to a human-readable address. Used by the
 * click-to-pin location flows (listing creation, "destination" confirmation before navigation). */
export async function reverseGeocode(point: {
  lat: number;
  lng: number;
}): Promise<GeocodeResult | null> {
  let ymaps;
  try {
    ymaps = await loadYandexMaps();
  } catch {
    return null;
  }
  let result;
  try {
    result = await ymaps.geocode([point.lat, point.lng], { results: 1 });
  } catch {
    return null;
  }
  const obj = result.geoObjects.get(0);
  return obj ? toGeocodeResult(obj) : null;
}
