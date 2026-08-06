/**
 * Free, keyless place/address search via OpenStreetMap's public Nominatim instance -- same
 * "public demo service, no account" pattern as the OSRM routing helper (`@/lib/routing`) and the
 * OSM/Esri/OpenTopoMap map tiles themselves. Nominatim's usage policy asks for light, interactive
 * (not bulk) traffic, which matches this app's "user types a place, gets suggestions" usage.
 */

export interface GeocodeResult {
  id: string;
  label: string;
  secondary?: string;
  lat: number;
  lng: number;
  kind: string;
  boundingBox?: { south: number; north: number; west: number; east: number };
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

let controller: AbortController | null = null;

/** Cancels any in-flight search before starting a new one -- callers fire this on every
 * keystroke, so stale slow responses must never clobber a newer, faster one. */
export async function searchPlaces(query: string, limit = 6): Promise<GeocodeResult[]> {
  const q = query.trim();
  if (q.length < 2) return [];

  controller?.abort();
  controller = new AbortController();

  const url =
    `https://nominatim.openstreetmap.org/search?format=jsonv2&addressdetails=0&limit=${limit}` +
    `&q=${encodeURIComponent(q)}`;

  let res: Response;
  try {
    res = await fetch(url, { signal: controller.signal, headers: { Accept: "application/json" } });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") return [];
    return [];
  }
  if (!res.ok) return [];

  const hits: NominatimHit[] = await res.json();
  return hits.map((h) => {
    const [south, north, west, east] = h.boundingbox.map(Number);
    const parts = h.display_name.split(",").map((p) => p.trim());
    return {
      id: String(h.place_id),
      label: parts[0] || h.display_name,
      secondary: parts.slice(1, 4).join(", "),
      lat: Number(h.lat),
      lng: Number(h.lon),
      kind: h.type || h.class,
      boundingBox: { south, north, west, east },
    };
  });
}
