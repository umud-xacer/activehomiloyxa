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
import {
  Building2,
  Sofa,
  Wrench,
  Package,
  Boxes,
  Blocks,
  Hammer,
  PaintBucket,
  Zap,
  Droplets,
  Layers,
  TreePine,
  Trees,
  BedDouble,
  UtensilsCrossed,
  Bath,
  Lamp,
  Ruler,
  Truck,
  Warehouse,
  Building,
  Landmark,
  Flower2,
  Waves,
  Mountain,
  Tent,
  Briefcase,
  HardHat,
  ShieldCheck,
  Car,
  DoorOpen,
  Shirt,
  Refrigerator,
  WashingMachine,
  Tv,
  AirVent,
  Armchair,
  Users,
  Laptop,
  Fence,
  Umbrella,
  Home,
  Tag,
  type LucideIcon,
} from "lucide-react";

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

/* -------------------------------------------------------------------------------------------
 * Category visual identity (icon + accent color) -- with ~100 seeded categories and no realistic
 * way to hand-source a unique photo for every subcategory, every category still gets a
 * consistent, on-theme visual: an admin-picked icon name (`descriptor.metadata.iconName`, see
 * `CategorySummary.iconName`) when set, otherwise a keyword match against the category's own
 * name, otherwise a generic tag. This is a general classification function, not a per-path
 * lookup table -- a brand-new admin-created category gets a sensible icon with zero code changes.
 * ------------------------------------------------------------------------------------------- */

/** Named registry an admin can reference by typing a name into the owner-admin panel's "Ikonka
 * nomi" field (`CategorySummary.iconName`) -- kept separate from `KIND_ICON` (kind-level, not
 * category-level) and from `iconUrl` (a real uploaded image, which always wins when present). */
export const ICON_BY_NAME: Record<string, LucideIcon> = {
  package: Package,
  boxes: Boxes,
  blocks: Blocks,
  hammer: Hammer,
  wrench: Wrench,
  "paint-bucket": PaintBucket,
  zap: Zap,
  droplets: Droplets,
  layers: Layers,
  "tree-pine": TreePine,
  trees: Trees,
  sofa: Sofa,
  "bed-double": BedDouble,
  utensils: UtensilsCrossed,
  bath: Bath,
  lamp: Lamp,
  ruler: Ruler,
  truck: Truck,
  warehouse: Warehouse,
  "building-2": Building2,
  building: Building,
  landmark: Landmark,
  flower: Flower2,
  waves: Waves,
  mountain: Mountain,
  tent: Tent,
  briefcase: Briefcase,
  "hard-hat": HardHat,
  "shield-check": ShieldCheck,
  car: Car,
  door: DoorOpen,
  shirt: Shirt,
  refrigerator: Refrigerator,
  "washing-machine": WashingMachine,
  tv: Tv,
  "air-vent": AirVent,
  armchair: Armchair,
  users: Users,
  laptop: Laptop,
  fence: Fence,
  umbrella: Umbrella,
  home: Home,
  tag: Tag,
};

/** First keyword match (checked in order) wins -- ordered roughly specific-to-generic so e.g.
 * "gishtli hovuz" matches "hovuz" (pool) before anything more generic. Uzbek category names only
 * (this app has no i18n'd category names in practice yet, per `categoryLabel`'s own fallback
 * chain), matched case-insensitively against substrings. */
const ICON_KEYWORD_RULES: Array<{ keywords: string[]; icon: LucideIcon }> = [
  { keywords: ["sement", "aralashma", "beton"], icon: Package },
  { keywords: ["g'isht", "gisht", "blok"], icon: Blocks },
  {
    keywords: [
      "armatura",
      "metall",
      "mahkamlash",
      "mix",
      "vint",
      "bolt",
      "gayka",
      "shayba",
      "dyubel",
      "anker",
      "shurup",
    ],
    icon: Hammer,
  },
  { keywords: ["yog'och", "yogoch", "fanera", "laminat"], icon: TreePine },
  { keywords: ["tom", "cherepitsa"], icon: Home },
  { keywords: ["issiqlik", "izolyatsiya", "gidro"], icon: Layers },
  { keywords: ["elektr", "kabel", "rozetka", "yoritish", "lampa", "chiroq"], icon: Zap },
  { keywords: ["santexnika", "suv", "gidravlik"], icon: Droplets },
  { keywords: ["bo'yoq", "boyoq", "lak", "grunt", "pardozlash"], icon: PaintBucket },
  { keywords: ["pol", "gilam", "qopla"], icon: Layers },
  { keywords: ["eshik", "deraza"], icon: DoorOpen },
  { keywords: ["asbob", "uskuna", "perforator", "drel"], icon: Wrench },
  { keywords: ["texnika", "jihoz"], icon: Truck },
  { keywords: ["furnitura", "ilgak", "mentesha", "rels", "qulf"], icon: Wrench },
  { keywords: ["oyoq", "tayanch"], icon: Sofa },
  { keywords: ["shisha", "oyna"], icon: Layers },
  { keywords: ["charm", "mato", "gazlama"], icon: Layers },
  { keywords: ["yelim", "kimyoviy"], icon: Package },
  { keywords: ["oshxona"], icon: UtensilsCrossed },
  { keywords: ["yotoqxona"], icon: BedDouble },
  { keywords: ["mehmonxona", "mehmon"], icon: Sofa },
  { keywords: ["bolalar"], icon: Users },
  { keywords: ["ofis"], icon: Briefcase },
  { keywords: ["yumshoq", "divan", "kreslo"], icon: Armchair },
  { keywords: ["bog'", "gazon", "landshaft", "yashil"], icon: Trees },
  { keywords: ["sug'orish"], icon: Droplets },
  { keywords: ["daraxt", "gul"], icon: Flower2 },
  { keywords: ["tosh", "yo'lak"], icon: Layers },
  { keywords: ["favvora", "suv havza"], icon: Waves },
  { keywords: ["pergola", "ayvon", "terassa", "gazebo"], icon: Umbrella },
  { keywords: ["hovuz", "basseyn", "spa", "sauna"], icon: Waves },
  { keywords: ["dekor", "bezak", "ko'zgu", "vaza", "haykal", "soat"], icon: Lamp },
  { keywords: ["parda", "jalyuzi"], icon: Layers },
  { keywords: ["muzlatgich"], icon: Refrigerator },
  { keywords: ["kir yuvish"], icon: WashingMachine },
  { keywords: ["idish yuvish"], icon: WashingMachine },
  { keywords: ["televizor"], icon: Tv },
  { keywords: ["konditsioner", "iqlim", "ventilyatsiya"], icon: AirVent },
  { keywords: ["issitkich"], icon: Zap },
  { keywords: ["changyutgich", "kichik maishiy"], icon: Package },
  { keywords: ["smart"], icon: Zap },
  { keywords: ["kiyim", "kurtka", "shim", "kombinezon", "jilet"], icon: Shirt },
  { keywords: ["poyabzal", "etik", "botinka"], icon: Shirt },
  { keywords: ["himoya", "kaska", "qo'lqop", "respirator", "niqob", "ko'zoynak"], icon: HardHat },
  { keywords: ["formasi"], icon: Shirt },
  { keywords: ["mavsumiy"], icon: Umbrella },
  { keywords: ["betonchi", "suvoqchi", "payvandchi", "quruvchi"], icon: HardHat },
  { keywords: ["elektrchi"], icon: Zap },
  { keywords: ["santexnik"], icon: Droplets },
  { keywords: ["arxitektura", "dizayner", "loyiha"], icon: Ruler },
  { keywords: ["agent"], icon: Briefcase },
  { keywords: ["sotuv", "marketing"], icon: Briefcase },
  { keywords: ["haydovchi"], icon: Car },
  { keywords: ["ombor", "logistika"], icon: Warehouse },
  { keywords: ["xavfsizlik"], icon: ShieldCheck },
  { keywords: ["tozalash"], icon: Sofa },
  { keywords: ["it ", "texnolog", "dasturchi", "backend", "frontend"], icon: Laptop },
  { keywords: ["moliya", "buxgalter"], icon: Briefcase },
  { keywords: ["menejment"], icon: Briefcase },
  { keywords: ["muhandis"], icon: Ruler },
  { keywords: ["villa", "kotej"], icon: Home },
  { keywords: ["tog'"], icon: Mountain },
  { keywords: ["ko'l", "daryo"], icon: Waves },
  { keywords: ["dala", "fermer", "qishloq xo'jaligi"], icon: Trees },
  { keywords: ["yer", "uchastka", "kadastr"], icon: Fence },
  { keywords: ["business center", "biznes markazi", "coworking"], icon: Briefcase },
  { keywords: ["savdo", "do'kon", "butik"], icon: Boxes },
  { keywords: ["restoran", "kafe"], icon: UtensilsCrossed },
  { keywords: ["zavod", "fabrika", "ishlab chiqarish"], icon: Warehouse },
  { keywords: ["tibbiyot", "shifoxona"], icon: ShieldCheck },
  { keywords: ["ta'lim", "maktab"], icon: Landmark },
  { keywords: ["avtoservis", "avtosalon"], icon: Car },
  { keywords: ["sport", "fitnes"], icon: Users },
  { keywords: ["hostel", "kapsula"], icon: BedDouble },
  { keywords: ["investitsiya", "investor"], icon: Landmark },
  { keywords: ["penthouse", "sky residence", "terrace"], icon: Building2 },
  { keywords: ["studio", "loft", "duplex"], icon: Home },
];

function keywordIcon(name: string): LucideIcon {
  const lower = name.toLowerCase();
  for (const rule of ICON_KEYWORD_RULES) {
    if (rule.keywords.some((k) => lower.includes(k))) return rule.icon;
  }
  return Tag;
}

/** Resolves a category's own icon: an admin-picked named icon first, then a keyword match
 * against its name, then the generic tag fallback. Never looks at ancestors -- unlike
 * `listingKind`/`accentColor`, an icon is meant to be specific to what the category actually is,
 * so "inheriting" a parent's icon would just be wrong (a screw isn't visually a construction
 * site). Use `resolveAccentColor` for the ancestor-inherited color to tint this icon's tile. */
export function resolveCategoryIcon(category: {
  name: Record<string, string>;
  iconName?: string | null;
}): LucideIcon {
  if (category.iconName && ICON_BY_NAME[category.iconName]) return ICON_BY_NAME[category.iconName];
  const name = category.name.uz_latn || Object.values(category.name)[0] || "";
  return keywordIcon(name);
}

const DEFAULT_ACCENT = "#6366f1";

/** Same ancestor-walk shape as `resolveListingKind` -- a subcategory almost never has its own
 * `accentColor`, so it inherits its nearest themed ancestor's color (keeps a whole category
 * family visually consistent, e.g. every "Qurilish materiallari" subcategory reads as the same
 * orange-industrial family) rather than falling back to one flat default for everything. */
export function resolveAccentColor(
  category: { id: string; parentId: string | null; accentColor?: string | null },
  byId: Map<string, { id: string; parentId: string | null; accentColor?: string | null }>,
): string {
  let current: typeof category | undefined = category;
  const seen = new Set<string>();
  while (current && !seen.has(current.id)) {
    if (current.accentColor) return current.accentColor;
    seen.add(current.id);
    current = current.parentId ? byId.get(current.parentId) : undefined;
  }
  return DEFAULT_ACCENT;
}

/** Same ancestor-walk shape as `resolveAccentColor` -- only the ~18 top-level and ~250
 * second-level categories are hand-themed with a real `heroImageUrl` (Task: category background
 * images); every deeper node inherits its nearest themed ancestor's photo + tagline together
 * (never mixing one ancestor's image with a different ancestor's caption) rather than falling
 * back to `PageHeader`'s plain icon-watermark gradient. Returns `{}` (both undefined) only if no
 * ancestor up to the root has one set yet -- `PageHeader` already handles that gracefully. */
export function resolveHeroImage(
  category: {
    id: string;
    parentId: string | null;
    heroImageUrl?: string | null;
    heroTagline?: string | null;
  },
  byId: Map<
    string,
    {
      id: string;
      parentId: string | null;
      heroImageUrl?: string | null;
      heroTagline?: string | null;
    }
  >,
): { heroImageUrl?: string; heroTagline?: string } {
  let current: typeof category | undefined = category;
  const seen = new Set<string>();
  while (current && !seen.has(current.id)) {
    if (current.heroImageUrl) {
      return { heroImageUrl: current.heroImageUrl, heroTagline: current.heroTagline ?? undefined };
    }
    seen.add(current.id);
    current = current.parentId ? byId.get(current.parentId) : undefined;
  }
  return {};
}
