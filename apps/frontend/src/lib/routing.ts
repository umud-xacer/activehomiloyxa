/**
 * Turn-by-turn directions via OSRM's public demo router (router.project-osrm.org) -- free, no
 * API key, no account. Same "keyless by design" constraint as the map tiles themselves (see
 * LeafletMapView's doc comment): the previous Google Maps integration broke because its key
 * belonged to infrastructure the user doesn't control.
 *
 * The demo server is rate-limited and not meant for production traffic at scale, but it's the
 * only zero-setup routing backend available and is sufficient for this app's usage pattern
 * (one route lookup per "Yo'lni boshlash" tap).
 */

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

type OsrmStep = {
  distance: number;
  duration: number;
  maneuver: { type: string; modifier?: string; location: [number, number] };
  name: string;
};

const MANEUVER_UZ: Record<string, string> = {
  depart: "Yo'lga chiqing",
  arrive: "Manzilga yetib keldingiz",
  turn: "Burilish",
  "new name": "Davom eting",
  continue: "To'g'ri davom eting",
  merge: "Qo'shiling",
  "on ramp": "Estakadaga chiqing",
  "off ramp": "Estakadadan tushing",
  fork: "Ayrilishda tanlang",
  "end of road": "Yo'l oxirida buriling",
  roundabout: "Aylanma yo'ldan o'ting",
  rotary: "Aylanma yo'ldan o'ting",
  "roundabout turn": "Aylanma yo'ldan buriling",
  "exit roundabout": "Aylanma yo'ldan chiqing",
  "exit rotary": "Aylanma yo'ldan chiqing",
};

const MODIFIER_UZ: Record<string, string> = {
  uturn: "U-burilish qiling",
  "sharp right": "keskin o'ngga buriling",
  right: "o'ngga buriling",
  "slight right": "biroz o'ngga buriling",
  straight: "to'g'ri davom eting",
  "slight left": "biroz chapga buriling",
  left: "chapga buriling",
  "sharp left": "keskin chapga buriling",
};

function describeStep(step: OsrmStep): string {
  const base = MANEUVER_UZ[step.maneuver.type] ?? "Davom eting";
  const modifier = step.maneuver.modifier ? MODIFIER_UZ[step.maneuver.modifier] : undefined;
  const road = step.name ? ` (${step.name})` : "";
  if (step.maneuver.type === "turn" && modifier) {
    return `${modifier.charAt(0).toUpperCase()}${modifier.slice(1)}${road}`;
  }
  if (modifier && step.maneuver.type !== "depart" && step.maneuver.type !== "arrive") {
    return `${base}, ${modifier}${road}`;
  }
  return `${base}${road}`;
}

export class RoutingError extends Error {}

export type TravelMode = "driving" | "walking";

/** Both are free, keyless public OSRM demo instances -- the default router.project-osrm.org only
 * mounts the "driving" profile, so walking directions come from the OSM Germany community's
 * public router instead (same non-commercial "light interactive use" policy as Nominatim/OSRM). */
const ROUTER_HOST: Record<TravelMode, { base: string; profile: string }> = {
  driving: { base: "https://router.project-osrm.org", profile: "driving" },
  walking: { base: "https://routing.openstreetmap.de/routed-foot", profile: "foot" },
};

/** Fetches a route between two points for the given travel mode. Throws `RoutingError` with a
 * user-facing (Uzbek) message on failure -- callers should catch and show it inline rather than
 * crash the map. */
export async function fetchRoute(
  from: { lat: number; lng: number },
  to: { lat: number; lng: number },
  mode: TravelMode = "driving",
): Promise<RouteResult> {
  const { base, profile } = ROUTER_HOST[mode];
  const url =
    `${base}/route/v1/${profile}/` +
    `${from.lng},${from.lat};${to.lng},${to.lat}` +
    `?overview=full&geometries=geojson&steps=true`;

  let res: Response;
  try {
    res = await fetch(url);
  } catch {
    throw new RoutingError("Marshrut xizmatiga ulanib bo'lmadi. Internet aloqasini tekshiring.");
  }
  if (!res.ok) {
    throw new RoutingError("Marshrutni hisoblab bo'lmadi. Birozdan so'ng qayta urinib ko'ring.");
  }
  const data = await res.json();
  if (data.code !== "Ok" || !data.routes?.[0]) {
    throw new RoutingError("Bu ikki nuqta orasida yo'l topilmadi.");
  }

  const route = data.routes[0];
  const coordinates: { lat: number; lng: number }[] = route.geometry.coordinates.map(
    ([lng, lat]: [number, number]) => ({ lat, lng }),
  );

  const steps: RouteStep[] = (route.legs?.[0]?.steps ?? []).map((s: OsrmStep) => ({
    instruction: describeStep(s),
    distanceMeters: s.distance,
    durationSeconds: s.duration,
    maneuverType: s.maneuver.type,
    maneuverModifier: s.maneuver.modifier,
    location: { lat: s.maneuver.location[1], lng: s.maneuver.location[0] },
  }));

  return {
    coordinates,
    distanceMeters: route.distance,
    durationSeconds: route.duration,
    steps,
  };
}

/** There is no free/keyless global public-transit routing API (schedules + transfers need GTFS
 * data and a paid or self-hosted engine) -- so "Jamoat transporti" deep-links out to Yandex Maps'
 * own transit directions instead of faking an embedded result (Yandex's transit/schedule coverage
 * for Uzbekistan and the wider CIS region is also generally stronger than alternatives). Same
 * honest "outbound link, no embed" pattern as the Street View link in `LeafletMapView`. */
export function transitDirectionsUrl(
  from: { lat: number; lng: number },
  to: { lat: number; lng: number },
): string {
  return `https://yandex.com/maps/?rtext=${from.lat},${from.lng}~${to.lat},${to.lng}&rtt=mt`;
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
