/**
 * Business-profiles API client — matches the "Business Profiles" section of
 * contracts/openapi.yaml (the real, already-implemented `profiles` module — BC-02).
 * Used by the legal-entity dashboard (ADR-0007's LEGAL_ENTITY workspace) and the
 * Landing Page / Business Profile edit form (`routes/dashboard/business-profile.tsx`).
 */
import {
  Armchair,
  Blocks,
  Boxes,
  Building,
  Building2,
  Calculator,
  Coins,
  Compass,
  Factory,
  Hammer,
  HardHat,
  Home,
  KeyRound,
  KeySquare,
  Landmark,
  Layers,
  PaintRoller,
  PenTool,
  Ruler,
  Settings2,
  ShieldCheck,
  Shield,
  Sofa,
  Sparkles,
  TrafficCone,
  Trees,
  Wrench,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { http } from "./http";

export type ProfileType =
  | "CONSTRUCTION_COMPANY"
  | "MANUFACTURER"
  | "BUILDER"
  | "SUPPLIER"
  | "CONTRACTOR"
  | "ARCHITECT"
  | "INTERIOR_DESIGNER"
  | "SERVICE_PROVIDER";

/** Additive (Organizations Main-Category task) — a second, independent sector classification
 * from `ProfileType`, used only for the public `/companies` directory's category tabs and the
 * mandatory onboarding-wizard selector. Two sectors (finance/mortgage, real-estate agencies)
 * have no corresponding `ProfileType` at all, which is why this isn't derived from that enum. */
export type MainCategory =
  | "FINANCE_MORTGAGE"
  | "CONSTRUCTION_CONTRACTORS"
  | "MANUFACTURERS_MATERIALS"
  | "ARCHITECTURE_INTERIOR"
  | "REPAIR_SERVICES"
  | "REAL_ESTATE_AGENCIES";

export const MAIN_CATEGORY_LABEL: Record<MainCategory, string> = {
  FINANCE_MORTGAGE: "Finans va Ipoteka",
  CONSTRUCTION_CONTRACTORS: "Qurilish kompaniyalari va Pudratchilar",
  MANUFACTURERS_MATERIALS: "Ishlab chiqaruvchilar va Materiallar",
  ARCHITECTURE_INTERIOR: "Arxitektura va Interyer dizayn",
  REPAIR_SERVICES: "Ta'mirlash va Xizmat ko'rsatuvchilar",
  REAL_ESTATE_AGENCIES: "Ko'chmas mulk agentliklari",
};

export const MAIN_CATEGORIES: MainCategory[] = [
  "FINANCE_MORTGAGE",
  "CONSTRUCTION_CONTRACTORS",
  "MANUFACTURERS_MATERIALS",
  "ARCHITECTURE_INTERIOR",
  "REPAIR_SERVICES",
  "REAL_ESTATE_AGENCIES",
];

/** URL slug for each `MainCategory` -- backs `/organizations/$categorySlug` (the dedicated
 * per-category directory page). Kept as an explicit map rather than derived from the label
 * (transliterating "Qurilish kompaniyalari va Pudratchilar" verbatim would produce an unwieldy
 * URL) -- short, stable, hand-picked instead. */
export const MAIN_CATEGORY_SLUG: Record<MainCategory, string> = {
  FINANCE_MORTGAGE: "finans-va-ipoteka",
  CONSTRUCTION_CONTRACTORS: "qurilish-kompaniyalari",
  MANUFACTURERS_MATERIALS: "ishlab-chiqaruvchilar",
  ARCHITECTURE_INTERIOR: "arxitektura-dizayn",
  REPAIR_SERVICES: "tamirlash-xizmatlari",
  REAL_ESTATE_AGENCIES: "kochmas-mulk",
};

const SLUG_TO_MAIN_CATEGORY: Record<string, MainCategory> = Object.fromEntries(
  MAIN_CATEGORIES.map((c) => [MAIN_CATEGORY_SLUG[c], c]),
) as Record<string, MainCategory>;

export function mainCategoryBySlug(slug: string): MainCategory | null {
  return SLUG_TO_MAIN_CATEGORY[slug] ?? null;
}

/** One representative photo per sector -- `MainCategory` is a fixed, admin-defined 6-value set
 * (unlike catalog categories, which come from the CMS and carry their own `heroImageUrl`), so a
 * photo is picked once here rather than sourced per organization. Shared by the homepage
 * `OrganizationsCarousel` and the `/organizations` hub page so both read as the same taxonomy. */
export const MAIN_CATEGORY_IMAGE: Record<MainCategory, string> = {
  FINANCE_MORTGAGE:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/9/99/500_East_Main_Street%28Norfolk%2C_Virginia%29.jpg/500px-500_East_Main_Street%28Norfolk%2C_Virginia%29.jpg",
  CONSTRUCTION_CONTRACTORS:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f3/Tower_crane_at_a_building_construction_site_in_Taichung_2023-05-13_01.jpg/500px-Tower_crane_at_a_building_construction_site_in_Taichung_2023-05-13_01.jpg",
  MANUFACTURERS_MATERIALS:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/0/05/Silo_of_the_factory_%E2%80%9EProfix%22_Tetovo%2C_North_Macedonia.jpg/500px-Silo_of_the_factory_%E2%80%9EProfix%22_Tetovo%2C_North_Macedonia.jpg",
  ARCHITECTURE_INTERIOR:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7d/House_S_by_Minhwan_Park_%EB%B0%95%EB%AF%BC%ED%99%98_%EA%B1%B4%EC%B6%95_S_%EC%A3%BC%ED%83%9D.jpg/500px-House_S_by_Minhwan_Park_%EB%B0%95%EB%AF%BC%ED%99%98_%EA%B1%B4%EC%B6%95_S_%EC%A3%BC%ED%83%9D.jpg",
  REPAIR_SERVICES:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/9/9c/Faubourg_Marigny%2C_New_Orleans_-_Interior_of_recently_renovated_house_-_04.jpg/500px-Faubourg_Marigny%2C_New_Orleans_-_Interior_of_recently_renovated_house_-_04.jpg",
  REAL_ESTATE_AGENCIES:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/4/49/Modern_living_room_with_stylish_furniture_and_a_view_of_the_outdoors_in_a_cozy_apartment_setting.jpg/500px-Modern_living_room_with_stylish_furniture_and_a_view_of_the_outdoors_in_a_cozy_apartment_setting.jpg",
};

/** One-line description per sector -- the hub grid card's subtitle and the detail page's own
 * header description. */
export const MAIN_CATEGORY_DESCRIPTION: Record<MainCategory, string> = {
  FINANCE_MORTGAGE: "Tijorat banklari, ipoteka markazlari va moliya tashkilotlari",
  CONSTRUCTION_CONTRACTORS: "Bosh pudratchilar, sub-pudratchilar va qurilish kompaniyalari",
  MANUFACTURERS_MATERIALS: "Qurilish materiallari va mebel ishlab chiqaruvchilar",
  ARCHITECTURE_INTERIOR: "Arxitektura, interyer va landshaft dizayn studiyalari",
  REPAIR_SERVICES: "Uy ta'mirlash, santexnika va boshqa xizmat ko'rsatuvchilar",
  REAL_ESTATE_AGENCIES: "Turar-joy va tijorat ko'chmas mulk agentliklari",
};

/** One accent color per sector -- 6-digit hex (not oklch/named) because `PageHeader` and the hub
 * grid card both append an alpha suffix directly to the string (`${accentColor}26`), which is
 * only well-formed for hex. Backs the `/organizations` hub cards and each
 * `/organizations/$categorySlug` page's `PageHeader` tint. */
export const MAIN_CATEGORY_ACCENT: Record<MainCategory, string> = {
  FINANCE_MORTGAGE: "#2563eb",
  CONSTRUCTION_CONTRACTORS: "#ea580c",
  MANUFACTURERS_MATERIALS: "#65a30d",
  ARCHITECTURE_INTERIOR: "#7c3aed",
  REPAIR_SERVICES: "#0891b2",
  REAL_ESTATE_AGENCIES: "#db2777",
};

/** Additive (Organizations Sub-Category task) -- a finer classification *within* one
 * `MainCategory` (e.g. "Tijorat banki" vs. "Ipoteka markazi", both under `FINANCE_MORTGAGE`).
 * Always optional, unlike `MainCategory` -- a profile can have a main category set and no
 * sub-category. See `SUB_CATEGORIES_BY_MAIN_CATEGORY` for which codes are legal under which
 * main category (mirrors the backend's own `profiles.domain.SUB_CATEGORIES_BY_MAIN_CATEGORY`). */
export type SubCategory =
  | "COMMERCIAL_BANK"
  | "MORTGAGE_CENTER"
  | "MICROFINANCE"
  | "INSURANCE"
  | "LEASING"
  | "GENERAL_CONTRACTOR"
  | "SUBCONTRACTOR"
  | "CIVIL_ENGINEERING"
  | "RENOVATION_CONTRACTOR"
  | "INFRASTRUCTURE_CONSTRUCTION"
  | "BUILDING_MATERIALS_MANUFACTURER"
  | "FURNITURE_MANUFACTURER"
  | "METAL_PRODUCTS_MANUFACTURER"
  | "CONCRETE_CEMENT_MANUFACTURER"
  | "GLASS_ALUMINUM_MANUFACTURER"
  | "ARCHITECTURE_STUDIO"
  | "INTERIOR_DESIGN_STUDIO"
  | "LANDSCAPE_DESIGN_STUDIO"
  | "ENGINEERING_DESIGN_STUDIO"
  | "HOME_REPAIR_SERVICE"
  | "PLUMBING_ELECTRICAL_SERVICE"
  | "CLEANING_SERVICE"
  | "APPLIANCE_REPAIR_SERVICE"
  | "RESIDENTIAL_AGENCY"
  | "COMMERCIAL_AGENCY"
  | "PROPERTY_MANAGEMENT"
  | "VALUATION_SERVICE";

export const SUB_CATEGORY_LABEL: Record<SubCategory, string> = {
  COMMERCIAL_BANK: "Tijorat banki",
  MORTGAGE_CENTER: "Ipoteka markazi",
  MICROFINANCE: "Mikromoliya tashkiloti",
  INSURANCE: "Sug'urta kompaniyasi",
  LEASING: "Lizing kompaniyasi",
  GENERAL_CONTRACTOR: "Bosh pudratchi",
  SUBCONTRACTOR: "Sub-pudratchi",
  CIVIL_ENGINEERING: "Muhandislik-qurilish",
  RENOVATION_CONTRACTOR: "Ta'mirlash pudratchisi",
  INFRASTRUCTURE_CONSTRUCTION: "Infratuzilma qurilishi",
  BUILDING_MATERIALS_MANUFACTURER: "Qurilish materiallari ishlab chiqaruvchi",
  FURNITURE_MANUFACTURER: "Mebel ishlab chiqaruvchi",
  METAL_PRODUCTS_MANUFACTURER: "Metall mahsulotlari ishlab chiqaruvchi",
  CONCRETE_CEMENT_MANUFACTURER: "Beton va sement ishlab chiqaruvchi",
  GLASS_ALUMINUM_MANUFACTURER: "Shisha va alyuminiy konstruksiyalar",
  ARCHITECTURE_STUDIO: "Arxitektura studiyasi",
  INTERIOR_DESIGN_STUDIO: "Interyer dizayn studiyasi",
  LANDSCAPE_DESIGN_STUDIO: "Landshaft dizayni studiyasi",
  ENGINEERING_DESIGN_STUDIO: "Muhandislik loyihalash",
  HOME_REPAIR_SERVICE: "Uy ta'mirlash xizmati",
  PLUMBING_ELECTRICAL_SERVICE: "Santexnika va elektr xizmati",
  CLEANING_SERVICE: "Tozalash xizmati",
  APPLIANCE_REPAIR_SERVICE: "Maishiy texnika ta'mirlash",
  RESIDENTIAL_AGENCY: "Turar-joy agentligi",
  COMMERCIAL_AGENCY: "Tijorat ko'chmas mulki agentligi",
  PROPERTY_MANAGEMENT: "Mulkni boshqarish",
  VALUATION_SERVICE: "Baholash xizmati",
};

/** One representative photo per sub-category, hand-verified (downloaded and visually checked, not
 * just keyword-matched) against Wikimedia Commons -- same sourcing convention as
 * `MAIN_CATEGORY_IMAGE`, never a random keyword-matched stock photo. Still a `Partial` in case a
 * future sub-category is added before a confidently-matching photo is found for it; every current
 * code has one (2026-08-20 premium visual pass filled in `PROPERTY_MANAGEMENT`/
 * `VALUATION_SERVICE`, the two that previously fell back to `SUB_CATEGORY_ICON`'s gradient+icon
 * tile). */
export const SUB_CATEGORY_IMAGE: Partial<Record<SubCategory, string>> = {
  COMMERCIAL_BANK:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e0/United_States_National_Bank_Building%2C_Portland%2C_Oregon_%282012%29_-_01.JPG/500px-United_States_National_Bank_Building%2C_Portland%2C_Oregon_%282012%29_-_01.JPG",
  MORTGAGE_CENTER:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d9/Fannie_Mae_Headquarters.JPG/500px-Fannie_Mae_Headquarters.JPG",
  MICROFINANCE:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4d/Aryavart_Gramin_Bank_Barabanki_Regional_Office.jpg/500px-Aryavart_Gramin_Bank_Barabanki_Regional_Office.jpg",
  INSURANCE:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/a/aa/New_York_Life_Insurance_Company_Building_from_east.jpg/500px-New_York_Life_Insurance_Company_Building_from_east.jpg",
  LEASING:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/5/57/FleetPride_Truck_%2838851789722%29.jpg/500px-FleetPride_Truck_%2838851789722%29.jpg",
  GENERAL_CONTRACTOR:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/7/76/Construction_Site.JPG/500px-Construction_Site.JPG",
  SUBCONTRACTOR:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/6/6a/Construction_Worker_Ladder_%2854070790%29.jpeg/500px-Construction_Worker_Ladder_%2854070790%29.jpeg",
  CIVIL_ENGINEERING:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/9/9a/Bridge_Construction_workers.jpg/500px-Bridge_Construction_workers.jpg",
  RENOVATION_CONTRACTOR:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/9/91/1._Warfield_House_Restoration._%2899cf7820-82fa-4113-8a7e-8a72abfacbdf%29.JPG/500px-1._Warfield_House_Restoration._%2899cf7820-82fa-4113-8a7e-8a72abfacbdf%29.JPG",
  INFRASTRUCTURE_CONSTRUCTION:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b9/Road_construction_in_progress.jpg/500px-Road_construction_in_progress.jpg",
  BUILDING_MATERIALS_MANUFACTURER:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/6/64/Brick_Factory_-_Kathmandu_-_Nepal_%2814515420731%29.jpg/500px-Brick_Factory_-_Kathmandu_-_Nepal_%2814515420731%29.jpg",
  FURNITURE_MANUFACTURER:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/4/45/Klein_Custom_Woodworking-_Two_Rivers%2C_WI_-_Flickr_-_MichaelSteeber.jpg/500px-Klein_Custom_Woodworking-_Two_Rivers%2C_WI_-_Flickr_-_MichaelSteeber.jpg",
  METAL_PRODUCTS_MANUFACTURER:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/7/79/Llanwern_Steel_works.jpg/500px-Llanwern_Steel_works.jpg",
  CONCRETE_CEMENT_MANUFACTURER:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e3/Holcim_cement_plant%2C_Portland%2C_Colorado.JPG/500px-Holcim_cement_plant%2C_Portland%2C_Colorado.JPG",
  GLASS_ALUMINUM_MANUFACTURER:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/4/41/Hallidie_Building_facade_2026_San_Francisco_dllu.jpg/500px-Hallidie_Building_facade_2026_San_Francisco_dllu.jpg",
  ARCHITECTURE_STUDIO:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3b/Interior_View_of_Drafting_Room_in_ERB_-_GPN-2000-001447.jpg/500px-Interior_View_of_Drafting_Room_in_ERB_-_GPN-2000-001447.jpg",
  INTERIOR_DESIGN_STUDIO:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/d/dd/Graphasel_Design_Studio_01.jpg/500px-Graphasel_Design_Studio_01.jpg",
  LANDSCAPE_DESIGN_STUDIO:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/6/69/Modern_Landscaped_Garden_Path_Along_Poolside_Perth_WA_2026.jpg/500px-Modern_Landscaped_Garden_Path_Along_Poolside_Perth_WA_2026.jpg",
  ENGINEERING_DESIGN_STUDIO:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/4/42/RCoE_-_mechanical_-_Workshop.jpg/500px-RCoE_-_mechanical_-_Workshop.jpg",
  HOME_REPAIR_SERVICE:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/2/20/The_Handyman%2C_Sandbeds%2C_Queensbury_%288702037721%29.jpg/500px-The_Handyman%2C_Sandbeds%2C_Queensbury_%288702037721%29.jpg",
  PLUMBING_ELECTRICAL_SERVICE:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/f/fa/Plumber_at_work.jpg/500px-Plumber_at_work.jpg",
  CLEANING_SERVICE:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/9/93/Window_Cleaner.jpg/500px-Window_Cleaner.jpg",
  APPLIANCE_REPAIR_SERVICE:
    "https://upload.wikimedia.org/wikipedia/commons/1/1e/Electronics_repair_shop_on_Lamington_Road.jpg",
  RESIDENTIAL_AGENCY:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b1/Joy_Lee_Apartments_Front.jpg/500px-Joy_Lee_Apartments_Front.jpg",
  COMMERCIAL_AGENCY:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/8/85/Bright_and_spacious_hallway_in_a_modern_office.jpg/500px-Bright_and_spacious_hallway_in_a_modern_office.jpg",
  PROPERTY_MANAGEMENT:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8e/2016-_The_Victoria_Towers%28%E6%B8%AF%E6%99%AF%E5%B3%B0%29%2C_Tsim_Sha_Tsui%2C_Hong_Kong_%28_Ank_Kumar_%29_01.jpg/500px-2016-_The_Victoria_Towers%28%E6%B8%AF%E6%99%AF%E5%B3%B0%29%2C_Tsim_Sha_Tsui%2C_Hong_Kong_%28_Ank_Kumar_%29_01.jpg",
  VALUATION_SERVICE:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/4/49/Couples_in_Real_Estate_Agent%27s_Office.jpg/500px-Couples_in_Real_Estate_Agent%27s_Office.jpg",
};

export const SUB_CATEGORIES_BY_MAIN_CATEGORY: Record<MainCategory, SubCategory[]> = {
  FINANCE_MORTGAGE: ["COMMERCIAL_BANK", "MORTGAGE_CENTER", "MICROFINANCE", "INSURANCE", "LEASING"],
  CONSTRUCTION_CONTRACTORS: [
    "GENERAL_CONTRACTOR",
    "SUBCONTRACTOR",
    "CIVIL_ENGINEERING",
    "RENOVATION_CONTRACTOR",
    "INFRASTRUCTURE_CONSTRUCTION",
  ],
  MANUFACTURERS_MATERIALS: [
    "BUILDING_MATERIALS_MANUFACTURER",
    "FURNITURE_MANUFACTURER",
    "METAL_PRODUCTS_MANUFACTURER",
    "CONCRETE_CEMENT_MANUFACTURER",
    "GLASS_ALUMINUM_MANUFACTURER",
  ],
  ARCHITECTURE_INTERIOR: [
    "ARCHITECTURE_STUDIO",
    "INTERIOR_DESIGN_STUDIO",
    "LANDSCAPE_DESIGN_STUDIO",
    "ENGINEERING_DESIGN_STUDIO",
  ],
  REPAIR_SERVICES: [
    "HOME_REPAIR_SERVICE",
    "PLUMBING_ELECTRICAL_SERVICE",
    "CLEANING_SERVICE",
    "APPLIANCE_REPAIR_SERVICE",
  ],
  REAL_ESTATE_AGENCIES: [
    "RESIDENTIAL_AGENCY",
    "COMMERCIAL_AGENCY",
    "PROPERTY_MANAGEMENT",
    "VALUATION_SERVICE",
  ],
};

/** Watermark/fallback-tile icon per sub-category -- shared by the `$categorySlug` grid's card
 * tiles and the `$subCategorySlug` detail page's `PageHeader` icon. */
export const SUB_CATEGORY_ICON: Record<SubCategory, LucideIcon> = {
  COMMERCIAL_BANK: Landmark,
  MORTGAGE_CENTER: KeyRound,
  MICROFINANCE: Coins,
  INSURANCE: Shield,
  LEASING: Building,
  GENERAL_CONTRACTOR: HardHat,
  SUBCONTRACTOR: Hammer,
  CIVIL_ENGINEERING: Ruler,
  RENOVATION_CONTRACTOR: PaintRoller,
  INFRASTRUCTURE_CONSTRUCTION: TrafficCone,
  BUILDING_MATERIALS_MANUFACTURER: Boxes,
  FURNITURE_MANUFACTURER: Armchair,
  METAL_PRODUCTS_MANUFACTURER: Factory,
  CONCRETE_CEMENT_MANUFACTURER: Blocks,
  GLASS_ALUMINUM_MANUFACTURER: Layers,
  ARCHITECTURE_STUDIO: Compass,
  INTERIOR_DESIGN_STUDIO: Sofa,
  LANDSCAPE_DESIGN_STUDIO: Trees,
  ENGINEERING_DESIGN_STUDIO: PenTool,
  HOME_REPAIR_SERVICE: Wrench,
  PLUMBING_ELECTRICAL_SERVICE: Zap,
  CLEANING_SERVICE: Sparkles,
  APPLIANCE_REPAIR_SERVICE: Settings2,
  RESIDENTIAL_AGENCY: Home,
  COMMERCIAL_AGENCY: Building,
  PROPERTY_MANAGEMENT: KeySquare,
  VALUATION_SERVICE: Calculator,
};

/** Generic placeholder icon for a `BusinessProfile` card with no logo yet -- shared by every
 * organization-listing surface (category grid, sub-category detail grid). */
export const ORGANIZATION_PLACEHOLDER_ICON: LucideIcon = Building2;
export const VERIFIED_BADGE_ICON: LucideIcon = ShieldCheck;

/** URL slug for each `SubCategory` -- backs `/organizations/$categorySlug/$subCategorySlug` (the
 * dedicated per-sub-category organizations directory). Explicit map, same convention as
 * `MAIN_CATEGORY_SLUG` (short, stable, hand-picked rather than derived from the label). */
export const SUB_CATEGORY_SLUG: Record<SubCategory, string> = {
  COMMERCIAL_BANK: "tijorat-banklari",
  MORTGAGE_CENTER: "ipoteka-markazlari",
  MICROFINANCE: "mikromoliya",
  INSURANCE: "sugurta",
  LEASING: "lizing",
  GENERAL_CONTRACTOR: "bosh-pudratchilar",
  SUBCONTRACTOR: "sub-pudratchilar",
  CIVIL_ENGINEERING: "muhandislik-qurilish",
  RENOVATION_CONTRACTOR: "tamirlash-pudratchilari",
  INFRASTRUCTURE_CONSTRUCTION: "infratuzilma-qurilishi",
  BUILDING_MATERIALS_MANUFACTURER: "qurilish-materiallari",
  FURNITURE_MANUFACTURER: "mebel-ishlab-chiqarish",
  METAL_PRODUCTS_MANUFACTURER: "metall-mahsulotlari",
  CONCRETE_CEMENT_MANUFACTURER: "beton-sement",
  GLASS_ALUMINUM_MANUFACTURER: "shisha-alyuminiy",
  ARCHITECTURE_STUDIO: "arxitektura-studiyalari",
  INTERIOR_DESIGN_STUDIO: "interyer-dizayn",
  LANDSCAPE_DESIGN_STUDIO: "landshaft-dizayni",
  ENGINEERING_DESIGN_STUDIO: "muhandislik-loyihalash",
  HOME_REPAIR_SERVICE: "uy-tamirlash",
  PLUMBING_ELECTRICAL_SERVICE: "santexnika-elektr",
  CLEANING_SERVICE: "tozalash-xizmati",
  APPLIANCE_REPAIR_SERVICE: "texnika-tamirlash",
  RESIDENTIAL_AGENCY: "turar-joy-agentligi",
  COMMERCIAL_AGENCY: "tijorat-mulk-agentligi",
  PROPERTY_MANAGEMENT: "mulkni-boshqarish",
  VALUATION_SERVICE: "baholash-xizmati",
};

const SLUG_TO_SUB_CATEGORY: Record<string, SubCategory> = Object.fromEntries(
  (Object.keys(SUB_CATEGORY_SLUG) as SubCategory[]).map((c) => [SUB_CATEGORY_SLUG[c], c]),
) as Record<string, SubCategory>;

/** Resolves a `$subCategorySlug` route param to a `SubCategory`, but only if it's actually a
 * legal sub-category of the given `MainCategory` -- guards against a URL like
 * `/organizations/finans-va-ipoteka/uy-tamirlash` (a real slug, wrong sector) resolving to a
 * cross-sector mismatch. */
export function subCategoryBySlug(mainCategory: MainCategory, slug: string): SubCategory | null {
  const resolved = SLUG_TO_SUB_CATEGORY[slug];
  if (!resolved) return null;
  return SUB_CATEGORIES_BY_MAIN_CATEGORY[mainCategory].includes(resolved) ? resolved : null;
}

export interface LocalizedText {
  uz_latn?: string;
  uz_cyrl?: string;
  ru?: string;
  en?: string;
}

export interface BusinessProfileBadge {
  status: "VALID" | "EXPIRED" | "REVOKED" | null;
  issuedAt?: string | null;
  validUntil?: string | null;
}

/** The `contacts` blob is a freeform JSONB VO in the backend (no fixed shape mandated) — this
 * is this frontend's own chosen convention for it, used consistently by create/update/read.
 * `workingHours`/`socialLinks` are additive (Portfolio & Navigation UI spec) — free text and
 * per-company channel URLs, no backend schema change needed since the field is freeform JSON. */
export interface BusinessProfileContacts {
  phones?: string[];
  emails?: string[];
  website?: string;
  workingHours?: string;
  socialLinks?: {
    telegram?: string;
    instagram?: string;
    facebook?: string;
  };
}

export interface PortfolioItem {
  id: string;
  mediaAssetId: string;
  position: number;
  caption?: LocalizedText | null;
}

export interface BusinessProfile {
  id: string;
  ownerUserId: string;
  profileType: ProfileType;
  name: LocalizedText;
  description?: LocalizedText | null;
  contacts?: BusinessProfileContacts | null;
  address?: string | null;
  slug?: string;
  status: "CREATED" | "ACTIVE" | "ARCHIVED";
  badge?: BusinessProfileBadge | null;
  portfolio?: PortfolioItem[];
  logoMediaAssetId?: string | null;
  bannerMediaAssetId?: string | null;
  subscriptionStatus: "ACTIVE" | "EXPIRED" | "NONE";
  subscriptionValidUntil?: string | null;
  /** ADR-0010. Null until the mandatory onboarding wizard (`routes/organization/setup.tsx`) is
   * completed — `requireOnboardedLegalEntity` redirects a LEGAL_ENTITY account there until set. */
  onboardingCompletedAt?: string | null;
  trialStartsAt?: string | null;
  trialEndsAt?: string | null;
  /** Additive (landing-page promo-video business rule). At most 2 media asset references, each
   * a video/mp4 or video/webm asset no longer than 30 seconds — resolve via `GET /media/{id}`,
   * same convention as `logoMediaAssetId`. */
  promoVideoMediaAssetIds?: string[];
  /** Additive (Organizations Main-Category task). Null on profiles that predate this field. */
  mainCategory?: MainCategory | null;
  /** Additive (Organizations Sub-Category task). Always optional -- null whenever not set. */
  subCategory?: SubCategory | null;
  createdAt?: string;
}

export interface SubmittedDocument {
  id?: string;
  mediaAssetId: string;
  documentKind: string;
  position?: number;
}

export interface VerificationCase {
  id: string;
  businessProfileId: string;
  entitlementId?: string;
  status: "REQUESTED" | "IN_REVIEW" | "APPROVED" | "REJECTED";
  slaDueAt?: string;
  documents?: SubmittedDocument[];
  decision?: { outcome: "APPROVED" | "REJECTED"; reason?: string; decidedAt: string } | null;
  createdAt?: string;
}

export const PROFILE_TYPE_LABEL: Record<ProfileType, string> = {
  CONSTRUCTION_COMPANY: "Qurilish kompaniyasi",
  MANUFACTURER: "Ishlab chiqaruvchi",
  BUILDER: "Quruvchi",
  SUPPLIER: "Yetkazib beruvchi",
  CONTRACTOR: "Pudratchi",
  ARCHITECT: "Arxitektor",
  INTERIOR_DESIGNER: "Interyer dizayneri",
  SERVICE_PROVIDER: "Xizmat ko'rsatuvchi",
};

interface UpdatePayload {
  name?: string;
  description?: string;
  contacts?: BusinessProfileContacts;
  address?: string;
  mainCategory?: MainCategory;
  subCategory?: SubCategory;
}

export const businessProfilesApi = {
  /** GET /business-profiles — the public companies directory. Client filters to
   * `subscriptionStatus === "ACTIVE"` (a lapsed subscription's profile stays readable by id --
   * e.g. by its own owner -- but shouldn't be discoverable in the public listing; see
   * `BusinessProfile.subscriptionStatus`'s own docstring for why this is a frontend-side filter
   * rather than a backend one). */
  listPublic(params?: {
    profileType?: ProfileType;
    mainCategory?: MainCategory;
    subCategory?: SubCategory;
    verifiedOnly?: boolean;
  }): Promise<BusinessProfile[]> {
    return http
      .get<{ items: BusinessProfile[] }>("/business-profiles", {
        params: {
          profileType: params?.profileType,
          mainCategory: params?.mainCategory,
          subCategory: params?.subCategory,
          verifiedOnly: params?.verifiedOnly,
          limit: 100,
        },
      })
      .then((page) => page.items);
  },

  /** GET /business-profiles/{id} — the profiles the account owns are read individually via
   * `Account.ownedProfileIds` (there is no "list mine" filter on the public listing endpoint). */
  get(profileId: string): Promise<BusinessProfile> {
    return http.get<BusinessProfile>(`/business-profiles/${profileId}`);
  },

  /** GET /business-profiles/slug/{slug} — ADR-0010. The public landing-page read
   * (`routes/companies/$slug.tsx`); unlike `get` above, 404s once the profile is not currently
   * entitled (trial lapsed, subscription lapsed, never onboarded). */
  getBySlug(slug: string): Promise<BusinessProfile> {
    return http.get<BusinessProfile>(`/business-profiles/slug/${slug}`);
  },

  create(input: {
    profileType: ProfileType;
    name: string;
    description?: string;
    contacts?: BusinessProfileContacts;
    address?: string;
    mainCategory?: MainCategory;
    subCategory?: SubCategory;
  }): Promise<BusinessProfile> {
    return http.post<BusinessProfile>(
      "/business-profiles",
      {
        profileType: input.profileType,
        name: { uz_latn: input.name },
        description: input.description ? { uz_latn: input.description } : undefined,
        contacts: input.contacts,
        address: input.address || undefined,
        mainCategory: input.mainCategory,
        subCategory: input.subCategory,
      },
      { idempotent: true },
    );
  },

  /** PATCH /business-profiles/{id} — partial update; `profileType` is immutable server-side. */
  update(profileId: string, input: UpdatePayload): Promise<BusinessProfile> {
    return http.patch<BusinessProfile>(`/business-profiles/${profileId}`, {
      name: input.name !== undefined ? { uz_latn: input.name } : undefined,
      description: input.description !== undefined ? { uz_latn: input.description } : undefined,
      contacts: input.contacts,
      address: input.address,
      mainCategory: input.mainCategory,
      subCategory: input.subCategory,
    });
  },

  archive(profileId: string): Promise<void> {
    return http.delete<void>(`/business-profiles/${profileId}`);
  },

  /** PATCH /business-profiles/{id}/branding — sets the landing page's logo/banner. `null`
   * clears the one it's passed for (see `BusinessProfileBrandingRequest`'s own docstring). */
  updateBranding(
    profileId: string,
    input: { logoMediaAssetId?: string | null; bannerMediaAssetId?: string | null },
  ): Promise<BusinessProfile> {
    return http.patch<BusinessProfile>(`/business-profiles/${profileId}/branding`, input);
  },

  listPortfolio(profileId: string): Promise<PortfolioItem[]> {
    return http.get<PortfolioItem[]>(`/business-profiles/${profileId}/portfolio`);
  },

  /** POST /business-profiles/{id}/portfolio — the wire contract's `PortfolioItem` schema marks
   * `id`/`position` required, but the backend use case ignores both (assigns its own id, always
   * appends) — see `profiles/interfaces/routers.py::add_portfolio_item`. Sent as throwaway
   * placeholder values purely to satisfy the frozen request-body shape. */
  addPortfolioItem(
    profileId: string,
    input: { mediaAssetId: string; caption?: string },
  ): Promise<PortfolioItem> {
    return http.post<PortfolioItem>(`/business-profiles/${profileId}/portfolio`, {
      id: crypto.randomUUID(),
      mediaAssetId: input.mediaAssetId,
      position: 1,
      caption: input.caption ? { uz_latn: input.caption } : undefined,
    });
  },

  removePortfolioItem(profileId: string, itemId: string): Promise<void> {
    return http.delete<void>(`/business-profiles/${profileId}/portfolio/${itemId}`);
  },

  /** POST /business-profiles/{id}/promo-videos — additive (landing-page promo-video business
   * rule). Backend re-validates the referenced asset is scanned CLEAN, video-typed, and 30
   * seconds or shorter server-side (never merely trusted from the client); returns the whole
   * updated profile (not just the new item) since there's no per-item id to hand back. */
  addPromoVideo(profileId: string, mediaAssetId: string): Promise<BusinessProfile> {
    return http.post<BusinessProfile>(`/business-profiles/${profileId}/promo-videos`, {
      mediaAssetId,
    });
  },

  removePromoVideo(profileId: string, mediaAssetId: string): Promise<void> {
    return http.delete<void>(`/business-profiles/${profileId}/promo-videos/${mediaAssetId}`);
  },

  /** POST /business-profiles/{id}/complete-onboarding — ADR-0010. Ends the mandatory onboarding
   * wizard and starts the 5-day free trial. Backend re-validates every mandatory field is
   * present (name/phone/logo/description/address/portfolio) — a 422 here means the wizard let
   * something through it shouldn't have. */
  completeOnboarding(profileId: string): Promise<BusinessProfile> {
    return http.post<BusinessProfile>(
      `/business-profiles/${profileId}/complete-onboarding`,
      {},
      { idempotent: true },
    );
  },

  getVerification(profileId: string): Promise<VerificationCase | null> {
    return http
      .get<VerificationCase>(`/business-profiles/${profileId}/verification`)
      .catch(() => null);
  },

  /** POST /business-profiles/{id}/verification — requires an active VERIFICATION_ELIGIBILITY
   * entitlement (billingApi.listMyEntitlements()) and at least one document. */
  requestVerification(
    profileId: string,
    input: { entitlementId: string; documents: SubmittedDocument[] },
  ): Promise<VerificationCase> {
    return http.post<VerificationCase>(`/business-profiles/${profileId}/verification`, input, {
      idempotent: true,
    });
  },
};

export interface BusinessProfilePage {
  items: BusinessProfile[];
  page: { limit: number; nextCursor: string | null; total: number | null };
}

/** Owner-admin panel's direct company-management surface (`profiles:profile:manage`,
 * gated the same "real check, not merely declared" way as `adminUsersApi`) — distinct from
 * `businessProfilesApi.listPublic` above, which only ever shows non-ARCHIVED companies to
 * anonymous visitors. */
export const adminBusinessProfilesApi = {
  list(params?: {
    status?: "CREATED" | "ACTIVE" | "ARCHIVED";
    cursor?: string;
    limit?: number;
  }): Promise<BusinessProfilePage> {
    return http.get<BusinessProfilePage>("/admin/business-profiles", { params });
  },

  archive(profileId: string): Promise<BusinessProfile> {
    return http.post<BusinessProfile>(
      `/admin/business-profiles/${profileId}/archive`,
      {},
      { idempotent: true },
    );
  },
};
