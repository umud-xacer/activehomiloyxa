/**
 * Direct catalog client — fetches listings by category path, unlike `apiClient.properties`
 * (which force-fits everything into the real-estate `Property` shape via `/search`). Used by
 * category pages whose listings aren't properties (construction materials, recreation venues).
 */
import { http } from "@/lib/http";

export interface CategorySummary {
  id: string;
  parentId: string | null;
  name: Record<string, string>;
  path: string;
  formDefinitionId: string;
  status: "ACTIVE" | "RETIRED";
  /** Set only when an admin uploaded a custom icon via the owner-admin panel; falls back to the
   * generic default icon (`CategoryCarousel.tsx`) when unset. */
  iconUrl?: string | null;
  /** Admin-authored per-category page theming (`owner-admin` panel) -- all optional, all fall
   * back to generic defaults when unset. See `lib/listing-kind.ts` for how `listingKind` drives
   * which shared template (`categories/$slug.tsx`) renders. */
  heroImageUrl?: string | null;
  heroTagline?: string | null;
  accentColor?: string | null;
  listingKind?: string | null;
  /** A named entry in `lib/listing-kind.ts`'s `ICON_BY_NAME` registry -- gives every category
   * (including subcategories with no uploaded photo) a themed icon instead of a bare fallback. */
  iconName?: string | null;
}

export interface CatalogListing {
  id: string;
  listingType: "ADVERTISEMENT" | "PRODUCT" | "SERVICE";
  categoryId: string;
  categoryPath?: string;
  title: string;
  description: string | null;
  /** The business profile that owns this listing, if it was posted under a company rather than a
   * personal account -- already on the public wire DTO (`catalog/interfaces/dto.py`'s `Listing`),
   * just not previously declared on this frontend type. Drives the "Top kompaniyalar" section
   * (`components/catalog/TopCompanies.tsx`) -- no backend change needed for that feature. */
  ownerProfileId?: string | null;
  /** The account that posted this listing -- always present on the backend DTO (`owner_user_id`,
   * required), used to hide the "contact seller" actions on a viewer's own listing. */
  ownerUserId?: string;
  attributes: Record<string, unknown>;
  price: { amount: string; currency: string } | null;
  location: { latitude: number; longitude: number } | null;
  images?: Array<{ id: string; mediaAssetId: string; position: number; status: string }>;
  slug: string;
  createdAt: string;
  lockVersion: number;
  lifecycleState?:
    | "DRAFT"
    | "PENDING_VERIFICATION"
    | "PUBLISHED"
    | "EDITED"
    | "SUSPENDED"
    | "ARCHIVED"
    | "DELETED";
}

export interface ListingsPage {
  items: CatalogListing[];
  page: { limit: number; nextCursor: string | null };
}

export interface FormFieldOption {
  value: string;
  label: Record<string, string>;
}

export interface FormField {
  code: string;
  label: Record<string, string>;
  fieldType:
    | "text"
    | "number"
    | "select"
    | "multiselect"
    | "boolean"
    | "date"
    | "range"
    | "location"
    | "file";
  required: boolean;
  order?: number;
  defaultValue?: unknown;
  options?: FormFieldOption[];
}

export interface FormSection {
  code: string;
  label: Record<string, string>;
  order: number;
  fields: FormField[];
}

export interface CategoryForm {
  id: string;
  versionId: string;
  categoryId: string;
  sections: FormSection[];
}

export interface ListingCreateInput {
  listingType: "ADVERTISEMENT" | "PRODUCT" | "SERVICE";
  categoryId: string;
  title: string;
  description?: string;
  attributes: Record<string, unknown>;
  price?: { amount: string; currency: string };
  location?: { latitude: number; longitude: number };
  imageMediaAssetIds?: string[];
  publish?: boolean;
}

export interface ListingUpdateInput {
  lockVersion: number;
  title?: string;
  description?: string;
  attributes?: Record<string, unknown>;
  price?: { amount: string; currency: string };
  location?: { latitude: number; longitude: number };
}

export type ListingStatusAction =
  "PUBLISH" | "ARCHIVE" | "SUSPEND" | "RENEW" | "RESTORE" | "DELETE";

export interface MediaUploadTicket {
  mediaAssetId: string;
  uploadUrl: string;
  method: string;
  headers?: Record<string, string>;
  expiresAt: string;
}

let categoriesCache: Promise<CategorySummary[]> | null = null;
let categoriesCacheAt = 0;
const CATEGORIES_CACHE_TTL_MS = 30_000;
/** Short TTL, not permanent: this module lives for the whole dev-server/SSR process lifetime,
 * not per-request, so a cache with no expiry would keep serving a category list from before the
 * last admin edit (add/retire/rename) until the process restarts. 30s bounds that staleness
 * while still deduping the several `listCategories()` calls a single page render triggers. */

/** `GET /categories?includeDescendants=true` returns every category at every depth in one round
 * trip (backend change: `CategoryReadUseCases.list_categories`'s cache read already fetches the
 * whole taxonomy regardless of the parent-level filter, so this was free to add). Replaced the
 * previous per-tree-node breadth-first walk (one `GET /categories?parentId=` request per node)
 * once the seeded taxonomy grew to 100+ categories and that walk started taking several seconds
 * and hundreds of requests to resolve on a cold cache -- confirmed live. */
async function fetchAllCategoriesFlat(): Promise<CategorySummary[]> {
  return http.get<CategorySummary[]>("/categories", { params: { includeDescendants: true } });
}

function fetchCategories(): Promise<CategorySummary[]> {
  const now = Date.now();
  if (!categoriesCache || now - categoriesCacheAt > CATEGORIES_CACHE_TTL_MS) {
    categoriesCache = fetchAllCategoriesFlat();
    categoriesCacheAt = now;
  }
  return categoriesCache;
}

export const catalogClient = {
  /** All categories, admin-managed via the Configuration module's category-versioning workflow. */
  async listCategories(): Promise<CategorySummary[]> {
    return fetchCategories();
  },

  async categoryByPath(path: string): Promise<CategorySummary | null> {
    const categories = await fetchCategories();
    // Trailing-slash URLs (bookmarks, external links, copy-paste) must still resolve -- stored
    // paths never carry one, so a bare `===` would 404 an otherwise-valid category.
    const normalized = path.length > 1 && path.endsWith("/") ? path.slice(0, -1) : path;
    return categories.find((c) => c.path === normalized) ?? null;
  },

  async listingsByCategoryPath(path: string, limit = 20): Promise<CatalogListing[]> {
    const category = await this.categoryByPath(path);
    if (!category) return [];
    const page = await http.get<ListingsPage>("/listings", {
      params: { categoryId: category.id, limit },
    });
    return page.items;
  },

  /** Cursor-paginated version of the above (real "load more" / infinite scroll, not a single
   * capped fetch) -- returns the full page envelope so the caller can keep requesting
   * `nextCursor` until it comes back `null`. Used by `CatalogDirectionView` (goods/service/venue
   * category pages) so a category with more than one page of listings doesn't silently truncate
   * at a fixed limit. */
  async listingsPageByCategoryId(
    categoryId: string,
    params: { cursor?: string | null; limit?: number } = {},
  ): Promise<ListingsPage> {
    return http.get<ListingsPage>("/listings", {
      params: { categoryId, cursor: params.cursor ?? undefined, limit: params.limit ?? 24 },
    });
  },

  /** GET /me/listings -- the authenticated account's own listings, any status. */
  async myListings(limit = 20): Promise<CatalogListing[]> {
    const page = await http.get<ListingsPage>("/me/listings", { params: { limit } });
    return page.items;
  },

  /** GET /listings/{id} -- a single listing in its raw catalog shape (attributes, lockVersion),
   * as opposed to `apiClient.properties.get()` which force-fits it into the real-estate `Property`
   * shape. Used by the edit-listing flow. */
  async getListing(listingId: string): Promise<CatalogListing> {
    return http.get<CatalogListing>(`/listings/${listingId}`);
  },

  /** GET /categories/{id}/form -- the dynamic attribute form bound to this category
   * (Configuration module's published FormDefinition). Public, no auth required. */
  async getCategoryForm(categoryId: string): Promise<CategoryForm> {
    return http.get<CategoryForm>(`/categories/${categoryId}/form`);
  },

  /** POST /listings -- server resolves the category's current published form binding and
   * validates `attributes` against it; no formDefinitionId/versionId to pass here. */
  async createListing(input: ListingCreateInput): Promise<CatalogListing> {
    return http.post<CatalogListing>("/listings", input, { idempotent: true });
  },

  /** PUT /listings/{id} -- `lockVersion` is required (optimistic concurrency; a stale value
   * throws ApiError with a 409). */
  async updateListing(listingId: string, input: ListingUpdateInput): Promise<CatalogListing> {
    return http.put<CatalogListing>(`/listings/${listingId}`, input);
  },

  /** DELETE /listings/{id} -- soft delete (lifecycle transition, no row removal). */
  async deleteListing(listingId: string): Promise<void> {
    return http.delete<void>(`/listings/${listingId}`);
  },

  /** POST /listings/{id}/status -- lifecycle transitions other than delete (publish/archive/
   * suspend/renew/restore). */
  async changeListingStatus(
    listingId: string,
    action: ListingStatusAction,
    reason?: string,
  ): Promise<CatalogListing> {
    return http.post<CatalogListing>(`/listings/${listingId}/status`, { action, reason });
  },

  /** POST /listings/{id}/images -- attaches one already-uploaded media asset as an image (there
   * is no bulk-attach on `PUT /listings/{id}`; images are managed through this separate
   * endpoint). */
  async attachListingImage(
    listingId: string,
    mediaAssetId: string,
  ): Promise<{ id: string; mediaAssetId: string; position: number }> {
    return http.post(`/listings/${listingId}/images`, { mediaAssetId });
  },

  /** DELETE /listings/{id}/images/{imageId} -- detaches an image (`imageId`, not `mediaAssetId`). */
  async detachListingImage(listingId: string, imageId: string): Promise<void> {
    return http.delete<void>(`/listings/${listingId}/images/${imageId}`);
  },

  /** POST /media/uploads -- requests a presigned upload slot; the caller must then PUT the raw
   * file bytes to `uploadUrl` (see `uploadMediaFile` below) before using `mediaAssetId`. */
  async initMediaUpload(file: File, ownerContextType = "LISTING"): Promise<MediaUploadTicket> {
    return http.post<MediaUploadTicket>("/media/uploads", {
      contentType: file.type,
      sizeBytes: file.size,
      ownerContextType,
    });
  },
};

/** Uploads raw file bytes to a presigned storage URL from `initMediaUpload`. This is
 * intentionally NOT routed through `http` -- the target is object storage (MinIO), not an
 * `/api/v1` backend endpoint, and the body must be the raw file, not JSON. */
export async function uploadMediaFile(ticket: MediaUploadTicket, file: File): Promise<void> {
  const response = await fetch(ticket.uploadUrl, {
    method: ticket.method || "PUT",
    headers: { "Content-Type": file.type, ...ticket.headers },
    body: file,
  });
  if (!response.ok) {
    throw new Error(`Rasm yuklashda xatolik (status ${response.status})`);
  }
}

export function formatUzs(amount: string | undefined): string {
  if (!amount) return "";
  const n = Math.round(Number(amount));
  return `${n.toLocaleString("uz-UZ")} so'm`;
}
