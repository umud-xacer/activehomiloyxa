/**
 * Client-side filtering for a category's catalog listings (goods/service/venue directions).
 *
 * There's no faceted-search endpoint for these listing kinds yet -- `catalogClient.listingsByCategoryPath`
 * takes only `categoryId`/`limit` (see `catalog-client.ts`). Rather than block the whole "kategoriya
 * bo'yicha filtrlash" requirement on that backend work, this filters the already-fetched page
 * client-side against the category's own dynamic form fields, which is exactly the attribute set an
 * admin defined for that category in the owner-admin panel -- zero hardcoding, same as everything
 * else in this direction. Once a real faceted `/listings` query exists, `applyListingFilters` is the
 * one place to swap for a server round trip; the UI (`CategoryFilterPanel.tsx`) doesn't need to change.
 */
import type { CatalogListing } from "@/lib/catalog-client";

/** "business" = posted under a company (`ownerProfileId` set), "individual" = posted directly by
 * a personal account (`ownerProfileId` null) -- a real, already-on-the-wire distinction (see
 * `CatalogListing.ownerProfileId`'s own doc comment), not a fabricated category. */
export type SellerKind = "all" | "business" | "individual";

export interface ListingFilterState {
  attrs: Record<string, string[]>;
  priceMin: string;
  priceMax: string;
  sellerKind: SellerKind;
}

export function emptyFilterState(): ListingFilterState {
  return { attrs: {}, priceMin: "", priceMax: "", sellerKind: "all" };
}

function toNumber(v: unknown): number | null {
  const n = typeof v === "string" ? Number(v) : typeof v === "number" ? v : NaN;
  return Number.isFinite(n) ? n : null;
}

export function applyListingFilters(
  listings: CatalogListing[],
  state: ListingFilterState,
): CatalogListing[] {
  const min = state.priceMin ? Number(state.priceMin) : null;
  const max = state.priceMax ? Number(state.priceMax) : null;
  const activeAttrEntries = Object.entries(state.attrs).filter(([, v]) => v.length > 0);

  return listings.filter((listing) => {
    if (state.sellerKind === "business" && !listing.ownerProfileId) return false;
    if (state.sellerKind === "individual" && listing.ownerProfileId) return false;
    if (min != null || max != null) {
      const price = toNumber(listing.price?.amount);
      if (price == null) return false;
      if (min != null && price < min) return false;
      if (max != null && price > max) return false;
    }
    for (const [code, selected] of activeAttrEntries) {
      const raw = listing.attributes[code];
      const values = Array.isArray(raw) ? raw.map(String) : raw != null ? [String(raw)] : [];
      if (!values.some((v) => selected.includes(v))) return false;
    }
    return true;
  });
}

export function activeFilterCount(state: ListingFilterState): number {
  const attrCount = Object.values(state.attrs).filter((v) => v.length > 0).length;
  return (
    attrCount +
    (state.priceMin ? 1 : 0) +
    (state.priceMax ? 1 : 0) +
    (state.sellerKind !== "all" ? 1 : 0)
  );
}
