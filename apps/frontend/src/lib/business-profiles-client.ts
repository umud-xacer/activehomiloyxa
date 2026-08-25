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
  Briefcase,
  Building,
  Building2,
  Calculator,
  Car,
  Coins,
  Compass,
  Factory,
  FileText,
  Hammer,
  HardHat,
  Home,
  KeyRound,
  KeySquare,
  Landmark,
  Layers,
  PackageOpen,
  PaintRoller,
  PenTool,
  Ruler,
  Scale,
  Settings2,
  ShieldCheck,
  Shield,
  Smartphone,
  Sofa,
  Sparkles,
  Stamp,
  TrafficCone,
  Trees,
  Truck,
  UtensilsCrossed,
  Warehouse,
  Wind,
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
  | "REAL_ESTATE_AGENCIES"
  | "TRANSPORT_LOGISTICS"
  | "LEGAL_CONSULTING_ACCOUNTING"
  | "HOME_APPLIANCES_EQUIPMENT"
  | "HOSPITALITY_SERVICES";

export const MAIN_CATEGORY_LABEL: Record<MainCategory, string> = {
  FINANCE_MORTGAGE: "Finans va Ipoteka",
  CONSTRUCTION_CONTRACTORS: "Qurilish kompaniyalari va Pudratchilar",
  MANUFACTURERS_MATERIALS: "Ishlab chiqaruvchilar va Materiallar",
  ARCHITECTURE_INTERIOR: "Arxitektura va Interyer dizayn",
  REPAIR_SERVICES: "Ta'mirlash va Xizmat ko'rsatuvchilar",
  REAL_ESTATE_AGENCIES: "Ko'chmas mulk agentliklari",
  TRANSPORT_LOGISTICS: "Transport va Logistika",
  LEGAL_CONSULTING_ACCOUNTING: "Yuridik, Konsalting va Buxgalteriya",
  HOME_APPLIANCES_EQUIPMENT: "Maishiy texnika va Uskunalar",
  HOSPITALITY_SERVICES: "Mehmonxona va Mehmondo'stlik xizmatlari",
};

export const MAIN_CATEGORIES: MainCategory[] = [
  "FINANCE_MORTGAGE",
  "CONSTRUCTION_CONTRACTORS",
  "MANUFACTURERS_MATERIALS",
  "ARCHITECTURE_INTERIOR",
  "REPAIR_SERVICES",
  "REAL_ESTATE_AGENCIES",
  "TRANSPORT_LOGISTICS",
  "LEGAL_CONSULTING_ACCOUNTING",
  "HOME_APPLIANCES_EQUIPMENT",
  "HOSPITALITY_SERVICES",
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
  TRANSPORT_LOGISTICS: "transport-logistika",
  LEGAL_CONSULTING_ACCOUNTING: "yuridik-konsalting",
  HOME_APPLIANCES_EQUIPMENT: "maishiy-texnika",
  HOSPITALITY_SERVICES: "mehmonxona-xizmatlari",
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
    "https://upload.wikimedia.org/wikipedia/commons/thumb/e/ec/Standard_Bank_Branch_in_Cape_Town.jpg/500px-Standard_Bank_Branch_in_Cape_Town.jpg",
  CONSTRUCTION_CONTRACTORS:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/4/46/Tottenham_Hotspur_Football_Club_new_ground_construction_January_2018_01.jpg/500px-Tottenham_Hotspur_Football_Club_new_ground_construction_January_2018_01.jpg",
  MANUFACTURERS_MATERIALS:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/5/57/Factory_of_National_Cement_Share_Company.jpg/500px-Factory_of_National_Cement_Share_Company.jpg",
  ARCHITECTURE_INTERIOR:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/4/49/Bonn%2C_Post-Tower_--_2017_--_2128.jpg/500px-Bonn%2C_Post-Tower_--_2017_--_2128.jpg",
  REPAIR_SERVICES:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/d/dc/Kitchen_Renovation_Marlton_New_Jersey.jpg/500px-Kitchen_Renovation_Marlton_New_Jersey.jpg",
  REAL_ESTATE_AGENCIES:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/e/eb/Douglas_Elliman_CA_HQ.jpg/500px-Douglas_Elliman_CA_HQ.jpg",
  // ADR-0012's 4 new sectors: loremflickr (keyless, tag-based) rather than a hand-picked
  // Wikimedia file -- a real swap point for later curation, same "randomness accepted for now"
  // tradeoff `category_hero_image_fix_wip`'s own precedent already made for catalog categories.
  TRANSPORT_LOGISTICS: "https://loremflickr.com/500/333/logistics,truck",
  LEGAL_CONSULTING_ACCOUNTING: "https://loremflickr.com/500/333/lawoffice,office",
  HOME_APPLIANCES_EQUIPMENT: "https://loremflickr.com/500/333/appliances,electronics",
  HOSPITALITY_SERVICES: "https://loremflickr.com/500/333/hotel,hospitality",
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
  TRANSPORT_LOGISTICS: "Yuk tashish, kuryerlik va logistika xizmatlari",
  LEGAL_CONSULTING_ACCOUNTING: "Yuridik firmalar, buxgalteriya va biznes konsalting xizmatlari",
  HOME_APPLIANCES_EQUIPMENT: "Maishiy texnika do'konlari, elektronika va uskunalar ijarasi",
  HOSPITALITY_SERVICES: "Mehmonxonalar, tadbirlar maskani va sayohat agentliklari",
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
  TRANSPORT_LOGISTICS: "#f59e0b",
  LEGAL_CONSULTING_ACCOUNTING: "#0d9488",
  HOME_APPLIANCES_EQUIPMENT: "#dc2626",
  HOSPITALITY_SERVICES: "#9333ea",
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
  | "VALUATION_SERVICE"
  | "FREIGHT_TRANSPORT"
  | "COURIER_DELIVERY"
  | "CAR_RENTAL"
  | "LOGISTICS_WAREHOUSING"
  | "MOVING_SERVICES"
  | "LAW_FIRM"
  | "ACCOUNTING_FIRM"
  | "BUSINESS_CONSULTING"
  | "TAX_ADVISORY"
  | "NOTARY_SERVICES"
  | "HOME_APPLIANCE_STORE"
  | "ELECTRONICS_RETAILER"
  | "APPLIANCE_SERVICE_CENTER"
  | "EQUIPMENT_RENTAL"
  | "HVAC_EQUIPMENT_SUPPLIER"
  | "HOTEL_OPERATOR"
  | "GUESTHOUSE_OPERATOR"
  | "EVENT_VENUE"
  | "CATERING_SERVICE"
  | "TRAVEL_AGENCY";

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
  FREIGHT_TRANSPORT: "Yuk tashish",
  COURIER_DELIVERY: "Kuryerlik xizmati",
  CAR_RENTAL: "Avtomobil ijarasi",
  LOGISTICS_WAREHOUSING: "Logistika va ombor xizmatlari",
  MOVING_SERVICES: "Ko'chirish xizmatlari",
  LAW_FIRM: "Yuridik firma",
  ACCOUNTING_FIRM: "Buxgalteriya xizmati",
  BUSINESS_CONSULTING: "Biznes konsalting",
  TAX_ADVISORY: "Soliq maslahati",
  NOTARY_SERVICES: "Notarial xizmatlar",
  HOME_APPLIANCE_STORE: "Maishiy texnika do'koni",
  ELECTRONICS_RETAILER: "Elektronika do'koni",
  APPLIANCE_SERVICE_CENTER: "Texnika xizmat markazi",
  EQUIPMENT_RENTAL: "Uskunalar ijarasi",
  HVAC_EQUIPMENT_SUPPLIER: "Klimat texnikasi",
  HOTEL_OPERATOR: "Mehmonxona operatori",
  GUESTHOUSE_OPERATOR: "Gostevoy uy operatori",
  EVENT_VENUE: "Tadbirlar maskani",
  CATERING_SERVICE: "Ketering xizmati",
  TRAVEL_AGENCY: "Sayohat agentligi",
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
    "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3b/A_Simmons_Bank_location_in_Sweetwater%2C_Tennessee.jpg/500px-A_Simmons_Bank_location_in_Sweetwater%2C_Tennessee.jpg",
  MORTGAGE_CENTER:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/0/02/Mortgage_Sure_office_in_Caerphilly_-_geograph.org.uk_-_6022884.jpg/500px-Mortgage_Sure_office_in_Caerphilly_-_geograph.org.uk_-_6022884.jpg",
  MICROFINANCE:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f8/Community-based_savings_bank_in_Cambodia.jpg/500px-Community-based_savings_bank_in_Cambodia.jpg",
  INSURANCE:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d7/Building_of_the_head_office_of_the_insurance_company_IMPEX_INSURANCE.jpg/500px-Building_of_the_head_office_of_the_insurance_company_IMPEX_INSURANCE.jpg",
  LEASING:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e9/National_Leasing_Head_Office_Building.jpg/500px-National_Leasing_Head_Office_Building.jpg",
  GENERAL_CONTRACTOR:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/5/55/A_seaside_construction_site_in_Busan.jpg/500px-A_seaside_construction_site_in_Busan.jpg",
  SUBCONTRACTOR:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4c/FEMA_-_38954_-_A_worker_installs_a_blue_tarp_on_a_roof_in_Texas.jpg/500px-FEMA_-_38954_-_A_worker_installs_a_blue_tarp_on_a_roof_in_Texas.jpg",
  CIVIL_ENGINEERING:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/4/44/Matakohe_No.2_Bridge_under_construction.jpg/500px-Matakohe_No.2_Bridge_under_construction.jpg",
  RENOVATION_CONTRACTOR:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a9/California_Kitchen_Demo%2BReconstruction_08.jpg/500px-California_Kitchen_Demo%2BReconstruction_08.jpg",
  INFRASTRUCTURE_CONSTRUCTION:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5c/King%27s_Cross_Central_development_tower_cranes%2C_London%2C_England_01.jpg/500px-King%27s_Cross_Central_development_tower_cranes%2C_London%2C_England_01.jpg",
  BUILDING_MATERIALS_MANUFACTURER:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/6/69/Arnold_Laver_Timber_World_-_Pontefract_Road_-_geograph.org.uk_-_3725097.jpg/500px-Arnold_Laver_Timber_World_-_Pontefract_Road_-_geograph.org.uk_-_3725097.jpg",
  FURNITURE_MANUFACTURER:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c9/Berkey_and_Gay_Furniture_Company_Factory_-1.jpg/500px-Berkey_and_Gay_Furniture_Company_Factory_-1.jpg",
  METAL_PRODUCTS_MANUFACTURER:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/e/ed/A_metal_fabricator_cutting_metal_plate_in_to_shape.jpg/500px-A_metal_fabricator_cutting_metal_plate_in_to_shape.jpg",
  CONCRETE_CEMENT_MANUFACTURER:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/0/0e/Cement_Plant%2C_Brookshire%2C_Texas.jpg/500px-Cement_Plant%2C_Brookshire%2C_Texas.jpg",
  GLASS_ALUMINUM_MANUFACTURER:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/0/00/Nedal-aluminium_at_the_Amsterdam-Rijnkanaal_in_Utrecht.jpg/500px-Nedal-aluminium_at_the_Amsterdam-Rijnkanaal_in_Utrecht.jpg",
  ARCHITECTURE_STUDIO:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e2/Studio_Wing%2C_Paul_Schweiker_House_and_Studio%2C_Meacham_Road%2C_Schaumburg%2C_IL.jpg/500px-Studio_Wing%2C_Paul_Schweiker_House_and_Studio%2C_Meacham_Road%2C_Schaumburg%2C_IL.jpg",
  INTERIOR_DESIGN_STUDIO:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/e/ed/Apartment-in-Berlin-by-Dezest-design-01.jpg/500px-Apartment-in-Berlin-by-Dezest-design-01.jpg",
  LANDSCAPE_DESIGN_STUDIO:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/6/69/Modern_Landscaped_Garden_Path_Along_Poolside_Perth_WA_2026.jpg/500px-Modern_Landscaped_Garden_Path_Along_Poolside_Perth_WA_2026.jpg",
  ENGINEERING_DESIGN_STUDIO:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/8/89/Multiconsult.JPG/500px-Multiconsult.JPG",
  HOME_REPAIR_SERVICE:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/5/51/Handyman_measuring_a_board.jpg/500px-Handyman_measuring_a_board.jpg",
  PLUMBING_ELECTRICAL_SERVICE:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/d/df/Plumber_at_work_2010_USA.jpg/500px-Plumber_at_work_2010_USA.jpg",
  CLEANING_SERVICE:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5b/Cleaning_service-1229.jpg/500px-Cleaning_service-1229.jpg",
  APPLIANCE_REPAIR_SERVICE:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/3/33/Person_repairs_a_kitchen_appliance_in_a_home_kitchen.jpg/500px-Person_repairs_a_kitchen_appliance_in_a_home_kitchen.jpg",
  RESIDENTIAL_AGENCY:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c4/Commercial_cleaning_Sydney.jpg/500px-Commercial_cleaning_Sydney.jpg",
  COMMERCIAL_AGENCY:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/8/85/Bright_and_spacious_hallway_in_a_modern_office.jpg/500px-Bright_and_spacious_hallway_in_a_modern_office.jpg",
  PROPERTY_MANAGEMENT:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8e/2016-_The_Victoria_Towers%28%E6%B8%AF%E6%99%AF%E5%B3%B0%29%2C_Tsim_Sha_Tsui%2C_Hong_Kong_%28_Ank_Kumar_%29_01.jpg/500px-2016-_The_Victoria_Towers%28%E6%B8%AF%E6%99%AF%E5%B3%B0%29%2C_Tsim_Sha_Tsui%2C_Hong_Kong_%28_Ank_Kumar_%29_01.jpg",
  VALUATION_SERVICE:
    "https://upload.wikimedia.org/wikipedia/commons/thumb/4/49/Couples_in_Real_Estate_Agent%27s_Office.jpg/500px-Couples_in_Real_Estate_Agent%27s_Office.jpg",
  // ADR-0012's 20 new sub-categories: loremflickr, same swap-point convention as
  // `MAIN_CATEGORY_IMAGE`'s own 4 new entries above.
  FREIGHT_TRANSPORT: "https://loremflickr.com/500/333/freight,truck",
  COURIER_DELIVERY: "https://loremflickr.com/500/333/courier,delivery",
  CAR_RENTAL: "https://loremflickr.com/500/333/carrental,cars",
  LOGISTICS_WAREHOUSING: "https://loremflickr.com/500/333/warehouse,logistics",
  MOVING_SERVICES: "https://loremflickr.com/500/333/moving,movers",
  LAW_FIRM: "https://loremflickr.com/500/333/lawfirm,office",
  ACCOUNTING_FIRM: "https://loremflickr.com/500/333/accounting,office",
  BUSINESS_CONSULTING: "https://loremflickr.com/500/333/consulting,meeting",
  TAX_ADVISORY: "https://loremflickr.com/500/333/tax,finance",
  NOTARY_SERVICES: "https://loremflickr.com/500/333/notary,document",
  HOME_APPLIANCE_STORE: "https://loremflickr.com/500/333/appliancestore,electronics",
  ELECTRONICS_RETAILER: "https://loremflickr.com/500/333/electronics,store",
  APPLIANCE_SERVICE_CENTER: "https://loremflickr.com/500/333/repair,technician",
  EQUIPMENT_RENTAL: "https://loremflickr.com/500/333/equipment,rental",
  HVAC_EQUIPMENT_SUPPLIER: "https://loremflickr.com/500/333/hvac,airconditioner",
  HOTEL_OPERATOR: "https://loremflickr.com/500/333/hotel,lobby",
  GUESTHOUSE_OPERATOR: "https://loremflickr.com/500/333/guesthouse,bnb",
  EVENT_VENUE: "https://loremflickr.com/500/333/eventvenue,banquet",
  CATERING_SERVICE: "https://loremflickr.com/500/333/catering,food",
  TRAVEL_AGENCY: "https://loremflickr.com/500/333/travel,agency",
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
  TRANSPORT_LOGISTICS: [
    "FREIGHT_TRANSPORT",
    "COURIER_DELIVERY",
    "CAR_RENTAL",
    "LOGISTICS_WAREHOUSING",
    "MOVING_SERVICES",
  ],
  LEGAL_CONSULTING_ACCOUNTING: [
    "LAW_FIRM",
    "ACCOUNTING_FIRM",
    "BUSINESS_CONSULTING",
    "TAX_ADVISORY",
    "NOTARY_SERVICES",
  ],
  HOME_APPLIANCES_EQUIPMENT: [
    "HOME_APPLIANCE_STORE",
    "ELECTRONICS_RETAILER",
    "APPLIANCE_SERVICE_CENTER",
    "EQUIPMENT_RENTAL",
    "HVAC_EQUIPMENT_SUPPLIER",
  ],
  HOSPITALITY_SERVICES: [
    "HOTEL_OPERATOR",
    "GUESTHOUSE_OPERATOR",
    "EVENT_VENUE",
    "CATERING_SERVICE",
    "TRAVEL_AGENCY",
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
  FREIGHT_TRANSPORT: Truck,
  COURIER_DELIVERY: Boxes,
  CAR_RENTAL: Car,
  LOGISTICS_WAREHOUSING: Warehouse,
  MOVING_SERVICES: PackageOpen,
  LAW_FIRM: Scale,
  ACCOUNTING_FIRM: FileText,
  BUSINESS_CONSULTING: Briefcase,
  TAX_ADVISORY: Calculator,
  NOTARY_SERVICES: Stamp,
  HOME_APPLIANCE_STORE: Zap,
  ELECTRONICS_RETAILER: Smartphone,
  APPLIANCE_SERVICE_CENTER: Settings2,
  EQUIPMENT_RENTAL: Wrench,
  HVAC_EQUIPMENT_SUPPLIER: Wind,
  HOTEL_OPERATOR: Building2,
  GUESTHOUSE_OPERATOR: Home,
  EVENT_VENUE: Sparkles,
  CATERING_SERVICE: UtensilsCrossed,
  TRAVEL_AGENCY: Compass,
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
  FREIGHT_TRANSPORT: "yuk-tashish",
  COURIER_DELIVERY: "kuryerlik-xizmati",
  CAR_RENTAL: "avtomobil-ijarasi",
  LOGISTICS_WAREHOUSING: "logistika-ombor",
  MOVING_SERVICES: "kochirish-xizmati",
  LAW_FIRM: "yuridik-firma",
  ACCOUNTING_FIRM: "buxgalteriya-xizmati",
  BUSINESS_CONSULTING: "biznes-konsalting",
  TAX_ADVISORY: "soliq-maslahati",
  NOTARY_SERVICES: "notarial-xizmatlar",
  HOME_APPLIANCE_STORE: "maishiy-texnika-dokoni",
  ELECTRONICS_RETAILER: "elektronika-dokoni",
  APPLIANCE_SERVICE_CENTER: "texnika-xizmat-markazi",
  EQUIPMENT_RENTAL: "uskunalar-ijarasi",
  HVAC_EQUIPMENT_SUPPLIER: "klimat-texnikasi",
  HOTEL_OPERATOR: "mehmonxona-operatori",
  GUESTHOUSE_OPERATOR: "gostevoy-uy",
  EVENT_VENUE: "tadbirlar-maskani",
  CATERING_SERVICE: "ketering-xizmati",
  TRAVEL_AGENCY: "sayohat-agentligi",
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
  /** ADR-0012: PENDING_REVIEW (default for a new company, awaiting a reviewer decision) and
   * REJECTED (not terminal -- editing the profile resubmits it to PENDING_REVIEW) widen the
   * original CREATED/ACTIVE/ARCHIVED set. */
  status: "CREATED" | "PENDING_REVIEW" | "ACTIVE" | "REJECTED" | "ARCHIVED";
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
  /** ADR-0012 ("Bank/Finans bloki"): free-text ipoteka/kredit terms -- only meaningful (and only
   * rendered on the landing page) when `mainCategory === "FINANCE_MORTGAGE"`. */
  financeOfferDetails?: LocalizedText | null;
  /** ADR-0012: an external YouTube link, alongside (not replacing) `promoVideoMediaAssetIds`. */
  promoVideoYoutubeUrl?: string | null;
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

  /** PATCH /business-profiles/{id}/landing-extras — ADR-0012. Sets the finance-terms block and
   * YouTube promo link in one call, both applied verbatim (`null` clears that one), mirroring
   * `updateBranding`'s own shape. */
  updateLandingExtras(
    profileId: string,
    input: { financeOfferDetails?: string | null; promoVideoYoutubeUrl?: string | null },
  ): Promise<BusinessProfile> {
    return http.patch<BusinessProfile>(`/business-profiles/${profileId}/landing-extras`, {
      financeOfferDetails:
        input.financeOfferDetails !== undefined
          ? input.financeOfferDetails
            ? { uz_latn: input.financeOfferDetails }
            : null
          : undefined,
      promoVideoYoutubeUrl: input.promoVideoYoutubeUrl,
    });
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
    status?: BusinessProfile["status"];
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

  /** POST /admin/business-profiles/{id}/decision — ADR-0012. The "Yangi arizalar" admin tab's
   * approve/reject action on a PENDING_REVIEW company. Same profiles:profile:manage gate as
   * `archive` above. */
  decide(
    profileId: string,
    input: { outcome: "APPROVED" | "REJECTED"; reason?: string },
  ): Promise<BusinessProfile> {
    return http.post<BusinessProfile>(`/admin/business-profiles/${profileId}/decision`, input, {
      idempotent: true,
    });
  },
};

export interface VerificationCasePage {
  items: VerificationCase[];
  page: { limit: number; nextCursor: string | null };
}

/** `/admin/organizations`'s reviewer queue (2026-08-24) -- both endpoints already existed on the
 * backend (`profiles/interfaces/routers.py::list_verification_queue`/`decide_verification`,
 * reviewer-gated) with no frontend consumer at all until now. */
export const adminVerificationApi = {
  listQueue(params?: {
    status?: VerificationCase["status"];
    cursor?: string;
    limit?: number;
  }): Promise<VerificationCasePage> {
    return http.get<VerificationCasePage>("/admin/verification-queue", { params });
  },

  decide(
    caseId: string,
    input: { outcome: "APPROVED" | "REJECTED"; reason?: string },
  ): Promise<VerificationCase> {
    return http.post<VerificationCase>(`/admin/verification-queue/${caseId}/decision`, input, {
      idempotent: true,
    });
  },
};
