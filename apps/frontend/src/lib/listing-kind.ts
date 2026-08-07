/**
 * Which shape a category's listings should be queried/rendered through — shared between the
 * category list page (`routes/categories/$slug.tsx`) and the listing detail page
 * (`routes/listing/$listingId.tsx`) so both agree on the same category -> kind without duplicating
 * it. Real estate is served via `/search` and force-fit into the `Property` shape
 * (`catalog-client.ts`'s own docstring); the other three kinds go straight at
 * `catalogClient.listingsByCategoryPath` instead -- goods, a service-provider's public "CV", and a
 * venue, in that listing's own natural shape rather than a real-estate one.
 *
 * Backend-driven (`CategorySummary.listingKind`, admin-authored via the owner-admin panel's
 * category form, `descriptor.metadata.listingKind`) -- no path is hardcoded here. A category with
 * no `listingKind` set yet (or an unrecognized value) falls back to `"PROPERTY"`, matching the
 * backend DTO's own documented default.
 */
import { Building2, Sofa, Wrench, type LucideIcon } from "lucide-react";

export type ListingKind = "PROPERTY" | "GOODS" | "SERVICE" | "VENUE";

const KNOWN_KINDS: readonly ListingKind[] = ["PROPERTY", "GOODS", "SERVICE", "VENUE"];

function parseKind(raw: string | null | undefined): ListingKind | null {
  return raw && (KNOWN_KINDS as readonly string[]).includes(raw) ? (raw as ListingKind) : null;
}

/** Reads a category's OWN `listingKind` only -- does not look at ancestors. Prefer
 * `resolveListingKind` (below) wherever the full category list is available; this is only for
 * call sites that genuinely have just the one category (no tree to walk). */
export function listingKindOf(category: { listingKind?: string | null }): ListingKind {
  return parseKind(category.listingKind) ?? "PROPERTY";
}

/** Walks up `parentId` until it finds a category with an explicit `listingKind`, defaulting to
 * `"PROPERTY"` only once the whole chain is exhausted. Most of this app's ~100 seeded categories
 * are subcategories with no metadata of their own (e.g. "qurilish-materiallari-mahkamlash-
 * mahsulotlari-gayka") -- without this walk, every one of them would silently render as a
 * PROPERTY-direction page regardless of what its top-level ancestor is admin-configured as. */
export function resolveListingKind(
  category: { id: string; parentId: string | null; listingKind?: string | null },
  byId: Map<string, { id: string; parentId: string | null; listingKind?: string | null }>,
): ListingKind {
  let current: typeof category | undefined = category;
  const seen = new Set<string>();
  while (current && !seen.has(current.id)) {
    const kind = parseKind(current.listingKind);
    if (kind) return kind;
    seen.add(current.id);
    current = current.parentId ? byId.get(current.parentId) : undefined;
  }
  return "PROPERTY";
}

export const KIND_EYEBROW: Record<Exclude<ListingKind, "PROPERTY">, string> = {
  GOODS: "Do'kon",
  SERVICE: "Xizmat ko'rsatuvchilar",
  VENUE: "Dam olish",
};

export const KIND_ICON: Record<Exclude<ListingKind, "PROPERTY">, LucideIcon> = {
  GOODS: Sofa,
  SERVICE: Wrench,
  VENUE: Building2,
};

/** Per-direction accent so a category "feels" like its own environment (industrial for goods,
 * professional-service blue for the CV directory, nature/travel green for venues) while staying
 * inside the existing design system's palette -- the enterprise spec (`active-home.pdf`) asks for
 * this "vizual muhit" per category without prescribing exact colors, and every category within a
 * kind shares its kind's environment (a `/tamirchi` page and a `/haydovchi` page both read as
 * "professional service"), which is consistent with the shared-template architecture. */
export const KIND_THEME: Record<
  Exclude<ListingKind, "PROPERTY">,
  { badge: string; icon: string }
> = {
  GOODS: {
    badge: "bg-amber-500/10 text-amber-600 dark:text-amber-400",
    icon: "bg-amber-500/10 text-amber-600 dark:text-amber-400",
  },
  SERVICE: {
    badge: "bg-blue-500/10 text-blue-600 dark:text-blue-400",
    icon: "bg-blue-500/10 text-blue-600 dark:text-blue-400",
  },
  VENUE: {
    badge: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
    icon: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  },
};
