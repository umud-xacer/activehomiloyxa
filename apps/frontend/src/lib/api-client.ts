import { http } from "@/lib/http";
import type {
  Paginated,
  Property,
  PropertyQuery,
  Agent,
  PropertyKind,
} from "@/features/properties/types";

const UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function isUuid(value: string): boolean {
  return UUID_REGEX.test(value);
}

const FALLBACK_AGENT: Agent = {
  id: "unknown-agent",
  name: "ActiveHome Agent",
  avatar:
    "https://images.unsplash.com/photo-1544005313-94ddf0286df2?auto=format&fit=crop&w=128&q=80",
  agency: "ActiveHome",
  rating: 4.6,
  reviews: 12,
  verified: true,
  phone: "",
  email: "",
  languages: ["en"],
};

function parseNumber(value: string | number | undefined, fallback = 0): number {
  if (value == null) return fallback;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function mapListingType(value: string | undefined): Property["listing_type"] {
  switch (value?.toUpperCase()) {
    case "PRODUCT":
      return "rent";
    case "SERVICE":
      return "short_stay";
    case "ADVERTISEMENT":
    default:
      return "sale";
  }
}

function mapPropertyKind(categoryPath?: string): PropertyKind {
  const normalized = String(categoryPath || "").toLowerCase();

  if (normalized.includes("apartment") || normalized.includes("apartments")) return "apartment";
  if (normalized.includes("house")) return "house";
  if (normalized.includes("cottage")) return "cottage";
  if (normalized.includes("commercial")) return "commercial";
  if (normalized.includes("land")) return "land";
  if (normalized.includes("hotel")) return "hotel";
  if (normalized.includes("hostel")) return "hostel";
  if (normalized.includes("building")) return "building";
  if (normalized.includes("country")) return "country";
  return "apartment";
}

function normalizeAddress(attributes: Record<string, unknown>, title: string): string {
  return (
    (attributes.address as string | undefined) ||
    (attributes.street as string | undefined) ||
    (attributes.location_description as string | undefined) ||
    title ||
    "Unknown address"
  );
}

function normalizeCity(attributes: Record<string, unknown>): string {
  return (
    (attributes.city as string | undefined) ||
    (attributes.town as string | undefined) ||
    (attributes.region as string | undefined) ||
    ""
  );
}

function normalizeCountry(attributes: Record<string, unknown>): string {
  return (attributes.country as string | undefined) || "";
}

function normalizeAmenities(attributes: Record<string, unknown>): string[] {
  if (Array.isArray(attributes.amenities)) return attributes.amenities as string[];
  return Object.entries(attributes)
    .filter(([key, value]) => typeof value === "boolean" && value)
    .map(([key]) => key.replace(/_/g, " "));
}

interface BackendProfile {
  id?: string;
  name?: string | Record<string, string>;
  avatar?: string;
  slug?: string;
  contacts?: { phone?: string; email?: string; [key: string]: unknown };
  badge?: { status?: string };
  languages?: string[];
}

function normalizeAgent(profile: BackendProfile | null): Agent {
  if (!profile) return FALLBACK_AGENT;

  const name =
    typeof profile.name === "string"
      ? profile.name
      : profile.name?.en || profile.name?.uz_latn || profile.name?.ru || "ActiveHome Agent";
  const contacts = profile.contacts || {};

  return {
    id: profile.id ?? "unknown-agent",
    name,
    avatar: profile.avatar ?? FALLBACK_AGENT.avatar,
    agency: profile.slug ?? (typeof profile.name === "string" ? profile.name : "ActiveHome"),
    rating: 4.6,
    reviews: 12,
    verified: profile.badge?.status === "VALID",
    phone: contacts.phone ?? "",
    email: contacts.email ?? "",
    languages: profile.languages ?? ["en"],
  };
}

function createPropertyFromBackend(
  listing: BackendListing,
  thumbnailUrl?: string | null,
  agent: Agent = FALLBACK_AGENT,
  mediaUrls: string[] = [],
): Property {
  const attributes = listing.attributes ?? {};
  const price = parseNumber(listing.price?.amount, 0);
  const area_m2 = parseNumber(attributes.area_m2 as string | number | undefined, 0);
  const bedrooms = parseNumber(attributes.rooms as string | number | undefined, 0);
  const bathrooms = parseNumber(attributes.bathrooms as string | number | undefined, 0);
  const kind = mapPropertyKind(listing.categoryPath);
  const listing_type = mapListingType(listing.listingType);
  const area = attributes.area as string | number | undefined;
  const year_built = attributes.year_built as string | number | undefined;
  const floor = attributes.floor as string | number | undefined;
  const floors_total = attributes.floors_total as string | number | undefined;
  const parking = attributes.parking as string | number | undefined;

  const media = mediaUrls.length
    ? mediaUrls.map((url, index) => ({
        id: `${listing.id}-${index}`,
        url,
        alt: listing.title,
        kind: "image" as const,
      }))
    : thumbnailUrl
      ? [
          {
            id: `${listing.id}-thumb`,
            url: thumbnailUrl,
            alt: listing.title,
            kind: "image" as const,
          },
        ]
      : [];

  return {
    id: listing.id,
    owner_user_id: listing.ownerUserId ?? "",
    slug: listing.slug,
    title: listing.title,
    description: listing.description ?? "",
    kind,
    listing_type,
    price,
    currency: (listing.price?.currency as Property["currency"]) || "USD",
    price_per_m2: area_m2 ? Math.round(price / Math.max(area_m2, 1)) : undefined,
    bedrooms,
    bathrooms,
    area_m2,
    year_built: parseNumber(year_built, new Date().getFullYear()),
    floor: parseNumber(floor, undefined),
    floors_total: parseNumber(floors_total, undefined),
    parking: parseNumber(parking, 1),
    furnished: attributes.furnished === true,
    amenities: normalizeAmenities(attributes),
    address: normalizeAddress(attributes, listing.title),
    city: normalizeCity(attributes),
    country: normalizeCountry(attributes),
    location: {
      lat: parseNumber(listing.location?.latitude, 0),
      lng: parseNumber(listing.location?.longitude, 0),
    },
    media,
    agent,
    ai_score: 78,
    ai_valuation: Math.round(price * 1.05),
    views: 0,
    favorites: 0,
    created_at: listing.createdAt,
    updated_at: listing.updatedAt,
    featured: listing.promotion != null,
    verified: listing.isFlagged !== true,
    reviews: [],
    rating: 4.6,
  };
}

function sortByDistance<T extends { location: { lat: number; lng: number } }>(
  items: T[],
  target: { lat: number; lng: number },
): T[] {
  return [...items].sort((a, b) => {
    const da = Math.hypot(a.location.lat - target.lat, a.location.lng - target.lng);
    const db = Math.hypot(b.location.lat - target.lat, b.location.lng - target.lng);
    return da - db;
  });
}

async function resolveMediaUrls(images: BackendListingImage[] | undefined): Promise<string[]> {
  if (!images?.length) return [];

  return Promise.all(
    images.map(async (image) => {
      try {
        const asset = await http.get<BackendMediaAsset>(`/media/${image.mediaAssetId}`);
        return asset.url || asset.variants?.[0]?.url || "";
      } catch {
        return "";
      }
    }),
  ).then((urls) => urls.filter(Boolean));
}

async function fetchBusinessProfile(profileId: string): Promise<BackendProfile | null> {
  try {
    return await http.get<BackendProfile>(`/business-profiles/${profileId}`);
  } catch {
    return null;
  }
}

async function fetchListingBySlug(slug: string): Promise<BackendListing | null> {
  const response = await http.get<BackendSearchResult>("/search", {
    params: { q: slug, limit: 20, sort: "RECENCY" },
  });
  const match = response.items.find((item) => item.slug === slug);
  if (!match) return null;
  return http.get<BackendListing>(`/listings/${match.listingId}`);
}

export const apiClient = {
  properties: {
    async list(query: PropertyQuery = {}): Promise<Paginated<Property>> {
      const page = query.page ?? 1;
      const page_size = query.page_size ?? 24;
      const limit = page * page_size;

      const params: Record<string, string | number | boolean | string[] | undefined> = {
        q: query.q,
        categoryId: query.category_id,
        listingType: query.listing_type
          ? query.listing_type === "rent"
            ? "PRODUCT"
            : query.listing_type === "short_stay"
              ? "SERVICE"
              : "ADVERTISEMENT"
          : undefined,
        priceMin: query.min_price != null ? String(query.min_price) : undefined,
        priceMax: query.max_price != null ? String(query.max_price) : undefined,
        fxUsdToUzs: query.fx_usd_to_uzs != null ? String(query.fx_usd_to_uzs) : undefined,
        sort: query.sort
          ? query.sort === "price_asc"
            ? "PRICE_ASC"
            : query.sort === "price_desc"
              ? "PRICE_DESC"
              : query.sort === "newest"
                ? "RECENCY"
                : "RELEVANCE"
          : "RELEVANCE",
        limit,
        "filters[city]": query.city,
        "filters[country]": query.country,
      };

      if (query.kind) {
        params["filters[kind]"] = Array.isArray(query.kind) ? query.kind : [query.kind];
      }
      if (query.amenities?.length) {
        params["filters[amenities]"] = query.amenities;
      }
      for (const [code, value] of Object.entries(query.filters ?? {})) {
        if (value) params[`filters[${code}]`] = value;
      }

      const response = await http.get<BackendSearchResult>("/search", { params });
      const items = response.items.slice((page - 1) * page_size, page * page_size);
      return {
        items: items.map((item) =>
          createPropertyFromBackend(
            {
              id: item.listingId,
              title: item.title,
              description: "",
              listingType: "ADVERTISEMENT",
              attributes: {},
              price: item.price,
              location: item.location,
              isFlagged: !item.verifiedBadge,
              images: [],
              slug: item.slug,
              createdAt: new Date().toISOString(),
              updatedAt: new Date().toISOString(),
            },
            item.thumbnailUrl,
          ),
        ),
        total: response.page.total ?? response.items.length,
        page,
        page_size,
      };
    },

    async get(idOrSlug: string): Promise<Property | null> {
      const listing = isUuid(idOrSlug)
        ? await http.get<BackendListing>(`/listings/${idOrSlug}`)
        : await fetchListingBySlug(idOrSlug);

      if (!listing) return null;

      const [mediaUrls, agentProfile] = await Promise.all([
        resolveMediaUrls(listing.images),
        listing.ownerProfileId
          ? fetchBusinessProfile(listing.ownerProfileId)
          : Promise.resolve(null),
      ]);

      return createPropertyFromBackend(
        listing,
        mediaUrls[0] ?? undefined,
        normalizeAgent(agentProfile),
        mediaUrls,
      );
    },

    async featured(limit = 8): Promise<Property[]> {
      const response = await http.get<BackendSearchResult>("/search", { params: { limit } });
      return response.items.map((item) =>
        createPropertyFromBackend(
          {
            id: item.listingId,
            title: item.title,
            description: "",
            listingType: "ADVERTISEMENT",
            attributes: {},
            price: item.price,
            location: item.location,
            isFlagged: !item.verifiedBadge,
            images: [],
            slug: item.slug,
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
          },
          item.thumbnailUrl,
        ),
      );
    },

    async nearby(id: string, limit = 6): Promise<Property[]> {
      const listing = isUuid(id)
        ? await http.get<BackendListing>(`/listings/${id}`)
        : await fetchListingBySlug(id);
      if (!listing) return [];

      const response = await http.get<BackendSearchResult>("/search", { params: { limit: 100 } });
      const hits = response.items
        .filter((item) => item.listingId !== listing.id)
        .map((item) =>
          createPropertyFromBackend(
            {
              id: item.listingId,
              title: item.title,
              description: "",
              listingType: "ADVERTISEMENT",
              attributes: {},
              price: item.price,
              location: item.location,
              isFlagged: !item.verifiedBadge,
              images: [],
              slug: item.slug,
              createdAt: new Date().toISOString(),
              updatedAt: new Date().toISOString(),
            },
            item.thumbnailUrl,
          ),
        );

      return sortByDistance(hits, {
        lat: listing.location.latitude,
        lng: listing.location.longitude,
      }).slice(0, limit);
    },
  },

  agents: {
    async list(): Promise<Agent[]> {
      return [FALLBACK_AGENT];
    },
    async get(id: string): Promise<Agent | null> {
      return FALLBACK_AGENT;
    },
  },

  /** Thin `/search` wrapper for map-marker-shaped data (id/title/price/location/thumbnail) --
   * `catalogClient` (lib/catalog-client.ts) only wraps `/listings` (exact `categoryId` match, no
   * geo, full `CatalogListing` payload for card rendering). This is the lean counterpart used
   * where only enough data to place a pin is needed: category/subcategory maps (`categoryPathPrefix`
   * aggregates a whole subtree, unlike `/listings`' exact match) and the global `/map` page's
   * "nearby this point" search (`lat`/`lng`/`radiusKm`). */
  catalog: {
    async search(params: {
      categoryId?: string;
      categoryPathPrefix?: string;
      q?: string;
      lat?: number;
      lng?: number;
      radiusKm?: number;
      cursor?: string | null;
      limit?: number;
      sort?: "RELEVANCE" | "RECENCY" | "PRICE_ASC" | "PRICE_DESC";
    }): Promise<{
      items: Array<{
        id: string;
        title: string;
        categoryPath: string;
        price?: { amount: string; currency: string };
        location?: { latitude: number; longitude: number };
        thumbnailUrl?: string;
        slug?: string;
      }>;
      nextCursor: string | null;
      total: number | null;
    }> {
      const response = await http.get<BackendSearchResult>("/search", {
        params: {
          categoryId: params.categoryId,
          categoryPathPrefix: params.categoryPathPrefix,
          q: params.q,
          lat: params.lat,
          lng: params.lng,
          radiusKm: params.radiusKm,
          cursor: params.cursor ?? undefined,
          limit: params.limit ?? 24,
          sort: params.sort ?? "RECENCY",
        },
      });
      return {
        items: response.items.map((item) => ({
          id: item.listingId,
          title: item.title,
          categoryPath: item.categoryPath,
          price: item.price,
          location: item.location,
          thumbnailUrl: item.thumbnailUrl ?? undefined,
          slug: item.slug,
        })),
        nextCursor: response.page.nextCursor,
        total: response.page.total,
      };
    },
  },
};

interface BackendListing {
  id: string;
  slug: string;
  title: string;
  description?: string | null;
  listingType?: string;
  categoryPath?: string;
  attributes?: Record<string, unknown>;
  price: { amount: string; currency: string };
  location: { latitude: number; longitude: number };
  isFlagged?: boolean;
  promotion?: { kind: string; validUntil: string } | null;
  images?: BackendListingImage[];
  createdAt: string;
  updatedAt: string;
  ownerUserId?: string | null;
  ownerProfileId?: string | null;
}

interface BackendListingImage {
  id: string;
  mediaAssetId: string;
  position: number;
  status: string;
}

interface BackendMediaAsset {
  id: string;
  url?: string | null;
  variants?: Array<{ kind: string; url: string; width: number; height: number }>;
}

interface BackendSearchResult {
  items: Array<{
    listingId: string;
    title: string;
    categoryPath: string;
    price: { amount: string; currency: string };
    location: { latitude: number; longitude: number };
    thumbnailUrl?: string | null;
    verifiedBadge?: boolean;
    promoted?: { kind: string } | null;
    slug: string;
  }>;
  page: { limit: number; nextCursor: string | null; total: number | null };
}
