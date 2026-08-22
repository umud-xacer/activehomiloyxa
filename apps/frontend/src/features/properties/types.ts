// Mirror of future DRF/FastAPI schemas. Keep field names snake_case-friendly via aliasing on the API client.

export type Currency = "USD" | "EUR" | "UZS" | "RUB" | "AED" | "GBP" | "TRY";

export type ListingType = "sale" | "rent" | "short_stay";

export type PropertyKind =
  | "apartment"
  | "house"
  | "cottage"
  | "building"
  | "commercial"
  | "country"
  | "land"
  | "hotel"
  | "hostel";

export interface GeoPoint {
  lat: number;
  lng: number;
}

export interface MediaItem {
  id: string;
  url: string;
  alt: string;
  kind: "image" | "video" | "tour_3d";
}

export interface Agent {
  id: string;
  name: string;
  avatar: string;
  agency?: string;
  rating: number;
  reviews: number;
  verified: boolean;
  phone: string;
  email: string;
  languages: string[];
}

export interface Review {
  id: string;
  author: string;
  avatar: string;
  rating: number;
  date: string; // ISO
  body: string;
}

export interface Property {
  id: string;
  owner_user_id: string;
  slug: string;
  title: string;
  description: string;
  kind: PropertyKind;
  listing_type: ListingType;
  price: number;
  currency: Currency;
  price_per_m2?: number;
  bedrooms: number;
  bathrooms: number;
  area_m2: number;
  year_built: number;
  floor?: number;
  floors_total?: number;
  parking: number;
  furnished: boolean;
  amenities: string[];
  address: string;
  city: string;
  country: string;
  location: GeoPoint;
  media: MediaItem[];
  agent: Agent;
  ai_score: number; // 0-100
  ai_valuation: number;
  views: number;
  favorites: number;
  created_at: string;
  updated_at: string;
  featured: boolean;
  verified: boolean;
  reviews: Review[];
  rating: number;
}

export interface PropertyQuery {
  q?: string;
  category_id?: string;
  city?: string;
  country?: string;
  kind?: PropertyKind | PropertyKind[];
  listing_type?: ListingType;
  min_price?: number;
  max_price?: number;
  min_bedrooms?: number;
  max_bedrooms?: number;
  min_area?: number;
  max_area?: number;
  amenities?: string[];
  /** Real per-category dynamic-field facets (`FormField.code` -> exact value), e.g.
   * `{ rooms: "3", condition: "new" }` for a real-estate category -- forwarded as-is to
   * `/search`'s `filters[code]=value` query params. Only fields the category's own form marks
   * `facetEligible: true` should ever end up here (see `FormField.facetEligible`'s doc comment);
   * the backend validates against the current facet config regardless. */
  filters?: Record<string, string>;
  bbox?: [number, number, number, number]; // [west, south, east, north]
  sort?: "newest" | "price_asc" | "price_desc" | "ai_score" | "popular";
  page?: number;
  page_size?: number;
}

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
