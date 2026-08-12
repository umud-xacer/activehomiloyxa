import { faker } from "@faker-js/faker";
import type {
  Agent,
  Property,
  PropertyKind,
  Review,
  ListingType,
  Currency,
} from "@/features/properties/types";

faker.seed(42);

const CITIES: Array<{ city: string; country: string; lat: number; lng: number }> = [
  { city: "Tashkent", country: "Uzbekistan", lat: 41.3111, lng: 69.2797 },
  { city: "Samarkand", country: "Uzbekistan", lat: 39.6542, lng: 66.9597 },
  { city: "Dubai", country: "UAE", lat: 25.2048, lng: 55.2708 },
  { city: "Istanbul", country: "Turkey", lat: 41.0082, lng: 28.9784 },
  { city: "London", country: "United Kingdom", lat: 51.5074, lng: -0.1278 },
  { city: "Berlin", country: "Germany", lat: 52.52, lng: 13.405 },
  { city: "New York", country: "United States", lat: 40.7128, lng: -74.006 },
  { city: "Singapore", country: "Singapore", lat: 1.3521, lng: 103.8198 },
  { city: "Tokyo", country: "Japan", lat: 35.6762, lng: 139.6503 },
  { city: "Bali", country: "Indonesia", lat: -8.3405, lng: 115.092 },
];

const KINDS: PropertyKind[] = [
  "apartment",
  "house",
  "cottage",
  "building",
  "commercial",
  "country",
  "land",
];
const LISTING: ListingType[] = ["sale", "rent", "short_stay"];
const CURRENCIES: Currency[] = ["USD", "EUR", "UZS", "AED", "GBP"];

const AMENITIES = [
  "pool",
  "gym",
  "parking",
  "elevator",
  "balcony",
  "garden",
  "security",
  "smart_home",
  "ac",
  "heating",
  "fireplace",
  "sauna",
  "concierge",
  "rooftop",
];

// Curated Unsplash collections — stable, real, premium imagery.
const PHOTO_POOLS = {
  apartment: [
    "photo-1545324418-cc1a3fa10c00",
    "photo-1502672260266-1c1ef2d93688",
    "photo-1493809842364-78817add7ffb",
    "photo-1560448204-e02f11c3d0e2",
    "photo-1522708323590-d24dbb6b0267",
    "photo-1505873242700-f289a29e1e0f",
  ],
  house: [
    "photo-1568605114967-8130f3a36994",
    "photo-1564013799919-ab600027ffc6",
    "photo-1600596542815-ffad4c1539a9",
    "photo-1580587771525-78b9dba3b914",
  ],
  cottage: [
    "photo-1518780664697-55e3ad937233",
    "photo-1505691938895-1758d7feb511",
    "photo-1499793983690-e29da59ef1c2",
  ],
  building: [
    "photo-1486325212027-8081e485255e",
    "photo-1554435493-93422e8d1a41",
    "photo-1502005229762-cf1b2da7c5d6",
  ],
  commercial: [
    "photo-1497366216548-37526070297c",
    "photo-1497366754035-f200968a6e72",
    "photo-1497215842964-222b430dc094",
  ],
  country: ["photo-1542718610-a1d656d1884c", "photo-1604014237800-1c9102c219da"],
  land: ["photo-1500382017468-9049fed747ef", "photo-1470770841072-f978cf4d019e"],
  hotel: [
    "photo-1566073771259-6a8506099945",
    "photo-1551882547-ff40c63fe5fa",
    "photo-1564501049412-61c2a3083791",
  ],
  hostel: ["photo-1555854877-bab0e564b8d5", "photo-1540541338287-41700207dee6"],
} satisfies Record<PropertyKind, string[]>;

function unsplash(id: string, w = 1600) {
  return `https://images.unsplash.com/${id}?auto=format&fit=crop&w=${w}&q=80`;
}

const AVATAR_IDS = [
  "photo-1535713875002-d1d0cf377fde",
  "photo-1573496359142-b8d87734a5a2",
  "photo-1438761681033-6461ffad8d80",
  "photo-1494790108377-be9c29b29330",
  "photo-1500648767791-00dcc994a43e",
  "photo-1517841905240-472988babdf9",
];

function makeAgent(): Agent {
  return {
    id: faker.string.uuid(),
    name: faker.person.fullName(),
    avatar: unsplash(faker.helpers.arrayElement(AVATAR_IDS), 400),
    agency: faker.company.name(),
    rating: faker.number.float({ min: 4, max: 5, fractionDigits: 1 }),
    reviews: faker.number.int({ min: 12, max: 480 }),
    verified: faker.datatype.boolean({ probability: 0.7 }),
    phone: faker.phone.number(),
    email: faker.internet.email().toLowerCase(),
    languages: faker.helpers.arrayElements(
      ["English", "Russian", "Uzbek", "Turkish", "Arabic", "German"],
      { min: 1, max: 3 },
    ),
  };
}

function makeReview(): Review {
  return {
    id: faker.string.uuid(),
    author: faker.person.fullName(),
    avatar: unsplash(faker.helpers.arrayElement(AVATAR_IDS), 200),
    rating: faker.number.int({ min: 4, max: 5 }),
    date: faker.date.recent({ days: 120 }).toISOString(),
    body: faker.lorem.sentences({ min: 1, max: 3 }),
  };
}

function makeProperty(i: number): Property {
  const place = faker.helpers.arrayElement(CITIES);
  const kind = faker.helpers.arrayElement(KINDS);
  const listing = faker.helpers.arrayElement(LISTING);
  const currency = faker.helpers.arrayElement(CURRENCIES);
  const area = faker.number.int({ min: 32, max: 480 });
  const basePrice =
    listing === "sale"
      ? faker.number.int({ min: 80_000, max: 4_800_000 })
      : listing === "rent"
        ? faker.number.int({ min: 400, max: 12_000 })
        : faker.number.int({ min: 60, max: 1_400 });

  const photoIds = faker.helpers.arrayElements(PHOTO_POOLS[kind] ?? PHOTO_POOLS.apartment, {
    min: 3,
    max: 6,
  });

  const title = `${faker.helpers.arrayElement([
    "Sunlit",
    "Panoramic",
    "Modern",
    "Heritage",
    "Skyline",
    "Garden",
    "Riverside",
    "Penthouse",
  ])} ${kind === "apartment" ? "apartment" : kind === "land" ? "plot" : kind} in ${place.city}`;

  const jitter = () => (Math.random() - 0.5) * 0.12;

  return {
    id: `prop_${i.toString().padStart(5, "0")}`,
    owner_user_id: `agent_${(i % 40).toString().padStart(3, "0")}`,
    slug: faker.helpers.slugify(`${title}-${i}`).toLowerCase(),
    title,
    description: faker.lorem.paragraphs({ min: 2, max: 4 }, "\n\n"),
    kind,
    listing_type: listing,
    price: basePrice,
    currency,
    price_per_m2: Math.round(basePrice / area),
    bedrooms: kind === "land" ? 0 : faker.number.int({ min: 1, max: 6 }),
    bathrooms: kind === "land" ? 0 : faker.number.int({ min: 1, max: 4 }),
    area_m2: area,
    year_built: faker.number.int({ min: 1985, max: 2025 }),
    floor: kind === "apartment" ? faker.number.int({ min: 1, max: 24 }) : undefined,
    floors_total:
      kind === "apartment" || kind === "building"
        ? faker.number.int({ min: 5, max: 40 })
        : undefined,
    parking: faker.number.int({ min: 0, max: 3 }),
    furnished: faker.datatype.boolean(),
    amenities: faker.helpers.arrayElements(AMENITIES, { min: 3, max: 8 }),
    address: faker.location.streetAddress(),
    city: place.city,
    country: place.country,
    location: { lat: place.lat + jitter(), lng: place.lng + jitter() },
    media: photoIds.map((pid, idx) => ({
      id: `${pid}-${idx}`,
      url: unsplash(pid, 1600),
      alt: `${title} — photo ${idx + 1}`,
      kind: "image" as const,
    })),
    agent: makeAgent(),
    ai_score: faker.number.int({ min: 62, max: 98 }),
    ai_valuation: Math.round(basePrice * faker.number.float({ min: 0.92, max: 1.12 })),
    views: faker.number.int({ min: 50, max: 14_000 }),
    favorites: faker.number.int({ min: 0, max: 800 }),
    created_at: faker.date.recent({ days: 60 }).toISOString(),
    updated_at: faker.date.recent({ days: 7 }).toISOString(),
    featured: faker.datatype.boolean({ probability: 0.18 }),
    verified: faker.datatype.boolean({ probability: 0.75 }),
    reviews: Array.from({ length: faker.number.int({ min: 0, max: 6 }) }, makeReview),
    rating: faker.number.float({ min: 4.1, max: 5, fractionDigits: 1 }),
  };
}

export const PROPERTIES: Property[] = Array.from({ length: 240 }, (_, i) => makeProperty(i));
export const AGENTS: Agent[] = Array.from({ length: 32 }, () => makeAgent());

export function findPropertyByIdOrSlug(idOrSlug: string): Property | undefined {
  return PROPERTIES.find((p) => p.id === idOrSlug || p.slug === idOrSlug);
}
