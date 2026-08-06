/**
 * Demo map data -- the backend's cross-category geo-search isn't ready yet (the catalog only has
 * a handful of real seeded listings, and the real-estate `/search` index is currently empty), so
 * the map would otherwise look broken/empty. This is a deliberately rich, hand-authored dataset
 * covering every category the map's filter bar exposes, spread across real Uzbekistan
 * coordinates, so the premium map experience (clustering, filters, navigation) has something
 * real to show right now.
 *
 * Swap point: `getDemoMapMarkers()` is the ONLY place that knows this data is fake. Once the
 * backend exposes a real cross-category geo-search endpoint, replace this function's body with
 * that fetch -- every caller (`/map`, the homepage preview) already treats it as an async call
 * and doesn't know or care where the markers come from.
 */
import type { FilterOption, MapMarker } from "@/components/map/LeafletMapView";

export const MAP_CATEGORIES: FilterOption[] = [
  { key: "apartment", label: "Kvartiralar", accent: "#6366F1" },
  { key: "house", label: "Uylar", accent: "#F59E0B" },
  { key: "commercial", label: "Tijorat", accent: "#64748B" },
  { key: "materials", label: "Qurilish mollari", accent: "#F97316" },
  { key: "recreation", label: "Dam olish maskanlari", accent: "#059669" },
  { key: "company", label: "Kompaniyalar", accent: "#8B5CF6" },
];

function uzs(amount: number): string {
  return `${amount.toLocaleString("en-US").replace(/,/g, " ")} so'm`;
}

type DemoSeed = Omit<MapMarker, "id" | "href"> & { slug: string };

const SEEDS: DemoSeed[] = [
  // Kvartiralar
  {
    slug: "kvartira-yunusobod",
    lat: 41.3495,
    lng: 69.2891,
    category: "apartment",
    accent: "#6366F1",
    title: "3 xonali kvartira, Yunusobod",
    subtitle: "Yunusobod tumani, Toshkent",
    label: uzs(850_000_000),
  },
  {
    slug: "kvartira-chilonzor",
    lat: 41.2833,
    lng: 69.2003,
    category: "apartment",
    accent: "#6366F1",
    title: "2 xonali kvartira, Chilonzor",
    subtitle: "Chilonzor tumani, Toshkent",
    label: uzs(620_000_000),
  },
  {
    slug: "kvartira-mirzo-ulugbek",
    lat: 41.3333,
    lng: 69.3167,
    category: "apartment",
    accent: "#6366F1",
    title: "1 xonali kvartira, Mirzo Ulug'bek",
    subtitle: "Mirzo Ulug'bek tumani, Toshkent",
    label: uzs(430_000_000),
  },
  {
    slug: "kvartira-yakkasaroy",
    lat: 41.2911,
    lng: 69.2401,
    category: "apartment",
    accent: "#6366F1",
    title: "4 xonali kvartira, Yakkasaroy",
    subtitle: "Yakkasaroy tumani, Toshkent",
    label: uzs(1_250_000_000),
  },
  {
    slug: "kvartira-sergeli",
    lat: 41.2258,
    lng: 69.2306,
    category: "apartment",
    accent: "#6366F1",
    title: "Yangi qurilgan kvartira, Sergeli",
    subtitle: "Sergeli tumani, Toshkent",
    label: uzs(380_000_000),
  },
  {
    slug: "kvartira-mirobod",
    lat: 41.3111,
    lng: 69.2797,
    category: "apartment",
    accent: "#6366F1",
    title: "Panorama kvartira, Mirobod",
    subtitle: "Mirobod tumani, Toshkent",
    label: uzs(990_000_000),
  },
  {
    slug: "kvartira-shayxontohur",
    lat: 41.3275,
    lng: 69.2412,
    category: "apartment",
    accent: "#6366F1",
    title: "Studiya kvartira, Shayxontohur",
    subtitle: "Shayxontohur tumani, Toshkent",
    label: uzs(320_000_000),
  },

  // Uylar
  {
    slug: "uy-zangiota",
    lat: 41.2018,
    lng: 69.1502,
    category: "house",
    accent: "#F59E0B",
    title: "Hovli uy, Zangiota tumani",
    subtitle: "Zangiota tumani, Toshkent viloyati",
    label: uzs(1_100_000_000),
  },
  {
    slug: "uy-qibray",
    lat: 41.3721,
    lng: 69.4218,
    category: "house",
    accent: "#F59E0B",
    title: "2 qavatli uy, Qibray",
    subtitle: "Qibray tumani, Toshkent viloyati",
    label: uzs(1_650_000_000),
  },
  {
    slug: "uy-bektemir",
    lat: 41.2214,
    lng: 69.3487,
    category: "house",
    accent: "#F59E0B",
    title: "Yangi hovli, Bektemir",
    subtitle: "Bektemir tumani, Toshkent",
    label: uzs(890_000_000),
  },
  {
    slug: "uy-parkent",
    lat: 41.4203,
    lng: 69.5487,
    category: "house",
    accent: "#F59E0B",
    title: "Dala hovlisi, Parkent yo'li",
    subtitle: "Parkent tumani, Toshkent viloyati",
    label: uzs(720_000_000),
  },
  {
    slug: "uy-villa",
    lat: 41.3502,
    lng: 69.5104,
    category: "house",
    accent: "#F59E0B",
    title: "Zamonaviy villa",
    subtitle: "Toshkent viloyati",
    label: uzs(2_400_000_000),
  },

  // Tijorat
  {
    slug: "ofis-amir-temur",
    lat: 41.3111,
    lng: 69.2856,
    category: "commercial",
    accent: "#64748B",
    title: "Ofis binosi, Amir Temur ko'chasi",
    subtitle: "Yunusobod tumani, Toshkent",
    label: uzs(3_200_000_000),
  },
  {
    slug: "dokon-chorsu",
    lat: 41.3264,
    lng: 69.2401,
    category: "commercial",
    accent: "#64748B",
    title: "Savdo do'koni, Chorsu yaqinida",
    subtitle: "Shayxontohur tumani, Toshkent",
    label: uzs(780_000_000),
  },
  {
    slug: "ombor-sergeli",
    lat: 41.2015,
    lng: 69.2198,
    category: "commercial",
    accent: "#64748B",
    title: "Ombor, Sergeli sanoat zonasi",
    subtitle: "Sergeli tumani, Toshkent",
    label: uzs(560_000_000),
  },
  {
    slug: "restoran-mirobod",
    lat: 41.3054,
    lng: 69.2912,
    category: "commercial",
    accent: "#64748B",
    title: "Restoran binosi, Mirobod",
    subtitle: "Mirobod tumani, Toshkent",
    label: uzs(1_450_000_000),
  },

  // Qurilish mollari
  {
    slug: "material-mix",
    lat: 41.311,
    lng: 69.279,
    category: "materials",
    accent: "#F97316",
    title: "Mix (turli o'lcham, 1 quti)",
    subtitle: "Qurilish mollari bozori",
    label: uzs(32_000),
  },
  {
    slug: "material-sement",
    lat: 41.301,
    lng: 69.25,
    category: "materials",
    accent: "#F97316",
    title: "Portlandsement M400, 50kg",
    subtitle: "Qurilish mollari bozori",
    label: uzs(58_000),
  },
  {
    slug: "material-armatura",
    lat: 41.29,
    lng: 69.26,
    category: "materials",
    accent: "#F97316",
    title: "Armatura A500S, 12mm",
    subtitle: "Qurilish mollari bozori",
    label: uzs(27_000),
  },
  {
    slug: "material-gisht",
    lat: 41.283,
    lng: 69.203,
    category: "materials",
    accent: "#F97316",
    title: "Silikat g'isht (oq)",
    subtitle: "Qurilish mollari bozori",
    label: uzs(850),
  },
  {
    slug: "material-boyoq",
    lat: 41.295,
    lng: 69.24,
    category: "materials",
    accent: "#F97316",
    title: "Fasad bo'yog'i, 20L",
    subtitle: "Qurilish mollari bozori",
    label: uzs(145_000),
  },

  // Dam olish maskanlari
  {
    slug: "chimyon-tog-kurorti",
    lat: 41.552,
    lng: 70.023,
    category: "recreation",
    accent: "#059669",
    title: "Chimyon tog' kurorti",
    subtitle: "Bo'stonliq tumani, Toshkent viloyati",
    label: uzs(450_000),
  },
  {
    slug: "aydarkol-turbaza",
    lat: 40.9,
    lng: 66.9,
    category: "recreation",
    accent: "#059669",
    title: "Aydarko'l bo'yidagi turbaza",
    subtitle: "Navoiy viloyati",
    label: uzs(350_000),
  },
  {
    slug: "chortoq-buloqlari",
    lat: 41.03,
    lng: 71.21,
    category: "recreation",
    accent: "#059669",
    title: "Chortoq issiq buloqlari",
    subtitle: "Namangan viloyati, Chortoq",
    label: uzs(280_000),
  },
  {
    slug: "zomin-bogi",
    lat: 39.95,
    lng: 68.4,
    category: "recreation",
    accent: "#059669",
    title: "Zomin milliy bog'i turbazasi",
    subtitle: "Jizzax viloyati, Zomin",
    label: uzs(300_000),
  },
  {
    slug: "fargona-maskani",
    lat: 40.4,
    lng: 71.7,
    category: "recreation",
    accent: "#059669",
    title: "Farg'ona vodiysi dam olish maskani",
    subtitle: "Farg'ona viloyati",
    label: uzs(320_000),
  },
  {
    slug: "nurota-lageri",
    lat: 40.56,
    lng: 65.68,
    category: "recreation",
    accent: "#059669",
    title: "Nurota tog'lari lageri",
    subtitle: "Navoiy viloyati, Nurota",
    label: uzs(250_000),
  },

  // Kompaniyalar
  {
    slug: "makro-build",
    lat: 41.32,
    lng: 69.28,
    category: "company",
    accent: "#8B5CF6",
    title: "Makro Build",
    subtitle: "Qurilish kompaniyasi",
    label: "Qurilish",
  },
  {
    slug: "premium-estate",
    lat: 41.31,
    lng: 69.27,
    category: "company",
    accent: "#8B5CF6",
    title: "Premium Estate",
    subtitle: "Ko'chmas mulk agentligi",
    label: "Agentlik",
  },
  {
    slug: "capital-bank",
    lat: 41.316,
    lng: 69.249,
    category: "company",
    accent: "#8B5CF6",
    title: "Capital Bank",
    subtitle: "Ipoteka bo'limi",
    label: "Ipoteka",
  },
  {
    slug: "atlas-developers",
    lat: 41.34,
    lng: 69.33,
    category: "company",
    accent: "#8B5CF6",
    title: "Atlas Developers",
    subtitle: "Devalopment kompaniyasi",
    label: "Devalopment",
  },
  {
    slug: "fix-master",
    lat: 41.27,
    lng: 69.21,
    category: "company",
    accent: "#8B5CF6",
    title: "Fix Master",
    subtitle: "Ta'mirlash xizmati",
    label: "Ta'mirlash",
  },
  {
    slug: "nova-interior",
    lat: 41.3,
    lng: 69.3,
    category: "company",
    accent: "#8B5CF6",
    title: "Nova Interior",
    subtitle: "Mebel va dizayn",
    label: "Mebel",
  },
];

const DEMO_MARKERS: MapMarker[] = SEEDS.map((s) => ({
  ...s,
  id: `demo-${s.slug}`,
  href: `/properties/demo-${s.slug}`,
}));

/** Async on purpose -- every caller already awaits this, so swapping the body for a real backend
 * call later is a one-line change with zero ripple effect on `/map` or the homepage preview. */
export async function getDemoMapMarkers(): Promise<MapMarker[]> {
  return DEMO_MARKERS;
}
