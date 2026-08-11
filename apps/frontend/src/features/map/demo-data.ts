/**
 * Map filter-bar category config, shared by `/map` and the homepage preview. `/map` now sources
 * every marker from real backend data (`apiClient.catalog.search`, `/search`'s `lat`/`lng`/
 * `radiusKm` geo-radius query -- see `map.tsx`) instead of the hand-authored demo set this file
 * used to hold; this is just the filter chip label/color config, kept separate because both the
 * property-marker builder (`toMarker` in `map.tsx`) and the nearby-search categorizer need to
 * agree on the same key set.
 */
import type { FilterOption } from "@/components/map/YandexMapView";

export const MAP_CATEGORIES: FilterOption[] = [
  { key: "apartment", label: "Kvartiralar", accent: "#6366F1" },
  { key: "house", label: "Uylar", accent: "#F59E0B" },
  { key: "commercial", label: "Tijorat", accent: "#64748B" },
  { key: "materials", label: "Qurilish mollari", accent: "#F97316" },
  { key: "recreation", label: "Dam olish maskanlari", accent: "#059669" },
];

/** Maps a listing's `categoryPath` (from a `/search` hit) to one of `MAP_CATEGORIES`' keys, for
 * the filter chip bar and pin accent color. Only the paths the chip bar actually exposes are
 * categorized -- everything else (services, hostels, jobs, ...) still shows on the map, it just
 * won't respond to these specific filter chips. */
export function categorizeByPath(categoryPath: string | undefined): string | undefined {
  if (!categoryPath) return undefined;
  if (categoryPath.startsWith("/qurilish-materiallari")) return "materials";
  if (categoryPath.startsWith("/dam-olish-maskanlari")) return "recreation";
  if (categoryPath.startsWith("/kotejlar") || categoryPath.startsWith("/hovlilar")) return "house";
  if (categoryPath.startsWith("/noturar-binolar")) return "commercial";
  if (categoryPath.startsWith("/kop-qavatli-binolar")) return "apartment";
  return undefined;
}
