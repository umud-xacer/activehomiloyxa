/**
 * Search API client — matches the "Search" section of contracts/openapi.yaml
 * (`GET/POST /search`, `GET /search/facets`, `GET /search/suggest`). Backs the global
 * search box (Navbar), the `/search` results page, and any category-scoped search box
 * that passes `categoryPathPrefix`.
 */
import { http } from "@/lib/http";

export interface SearchHit {
  listingId: string;
  title: string;
  categoryPath?: string;
  price?: { amount: string; currency: string };
  location?: { lat: number; lng: number };
  thumbnailUrl?: string | null;
  verifiedBadge?: boolean;
  promoted?: { kind: "PREMIUM" | "FEATURED" | "TOP_PLACEMENT" } | null;
  slug?: string;
}

export interface FacetBucket {
  value: string;
  count: number;
}

export interface Facet {
  fieldCode: string;
  label: Record<string, string>;
  buckets: FacetBucket[];
}

export interface SearchResult {
  items: SearchHit[];
  facets: Facet[];
  page: { limit: number; nextCursor: string | null; total: number | null };
  degraded?: boolean;
}

export type SuggestionType = "QUERY" | "CATEGORY" | "LISTING";

export interface Suggestion {
  text: string;
  type: SuggestionType;
  refId?: string | null;
}

export type SearchSort = "RELEVANCE" | "RECENCY" | "PRICE_ASC" | "PRICE_DESC";

export interface SearchParams {
  q?: string;
  categoryId?: string;
  /** Subtree match by category_path prefix -- use for a parent category page that should
   * aggregate its whole subtree; use categoryId for an exact leaf match instead. */
  categoryPathPrefix?: string;
  listingType?: "ADVERTISEMENT" | "PRODUCT" | "SERVICE";
  priceMin?: string;
  priceMax?: string;
  verifiedOnly?: boolean;
  sort?: SearchSort;
  cursor?: string;
  limit?: number;
  signal?: AbortSignal;
}

export const searchApi = {
  search({ signal, ...params }: SearchParams = {}): Promise<SearchResult> {
    return http.get<SearchResult>("/search", { params, signal });
  },
  suggest(q: string, limit = 5, signal?: AbortSignal): Promise<Suggestion[]> {
    if (!q.trim()) return Promise.resolve([]);
    return http.get<Suggestion[]>("/search/suggest", { params: { q, limit }, signal });
  },
  facets(categoryId?: string): Promise<Facet[]> {
    return http.get<Facet[]>("/search/facets", { params: { categoryId } });
  },
};
