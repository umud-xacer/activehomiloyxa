/**
 * Demo investment opportunities -- the backend has no dedicated "investment project" concept yet
 * (see ADR-0007: `INVESTOR` is only an account kind, orthogonal to `catalog`'s listing model).
 * This is deliberately structured like a real API response so the public `/invest` browsing
 * experience and each project's detail page have something real-feeling to show today.
 *
 * Swap point: `getInvestmentOpportunities()` / `getInvestmentOpportunity(slug)` are the only
 * places that know this data is fake. Once a real backend investment-project module exists,
 * replace their bodies with the real fetch -- callers already treat both as async.
 */

export type OpportunityCategory = "residential" | "commercial" | "hotel" | "industrial";

export interface InvestmentOpportunity {
  slug: string;
  title: string;
  city: string;
  category: OpportunityCategory;
  lat: number;
  lng: number;
  target: number;
  raised: number;
  roi: string;
  durationMonths: number;
  minInvestment: number;
  investorsCount: number;
  completionDate: string;
  image: string;
  description: string;
  highlights: string[];
}

export const CATEGORY_LABEL: Record<OpportunityCategory, string> = {
  residential: "Turar-joy",
  commercial: "Savdo",
  hotel: "Mehmonxona",
  industrial: "Sanoat",
};

const OPPORTUNITIES: InvestmentOpportunity[] = [
  {
    slug: "tashkent-city",
    title: "Tashkent City — turar-joy kompleksi",
    city: "Toshkent",
    category: "residential",
    lat: 41.3268,
    lng: 69.2775,
    target: 2_500_000_000,
    raised: 1_680_000_000,
    roi: "18%",
    durationMonths: 24,
    minInvestment: 25_000_000,
    investorsCount: 142,
    completionDate: "2027, II chorak",
    image:
      "https://images.unsplash.com/photo-1545324418-cc1a3fa10c00?auto=format&fit=crop&w=1200&q=80",
    description:
      "Toshkent markazidagi zamonaviy turar-joy majmuasi — 3 blok, 480 xonadon, yer osti avtoturargoh va butun hudud landshaft dizayni bilan. Loyiha qurilish kompaniyasi tomonidan bosqichma-bosqich amalga oshirilmoqda, hozirgi bosqich poydevor va karkas ishlari.",
    highlights: [
      "480 xonadon, 3 bino, yer osti avtoturargoh",
      "Qurilish litsenziyasi va yer huquqi tasdiqlangan",
      "Har chorakda progress hisoboti beriladi",
    ],
  },
  {
    slug: "samarqand-savdo-markazi",
    title: "Samarqand savdo markazi",
    city: "Samarqand",
    category: "commercial",
    lat: 39.6542,
    lng: 66.9597,
    target: 1_200_000_000,
    raised: 420_000_000,
    roi: "14%",
    durationMonths: 18,
    minInvestment: 15_000_000,
    investorsCount: 68,
    completionDate: "2026, IV chorak",
    image:
      "https://images.unsplash.com/photo-1487958449943-2429e8be8625?auto=format&fit=crop&w=1200&q=80",
    description:
      "Turistik markazga yaqin joylashgan 2 qavatli zamonaviy savdo majmuasi. 60 dan ortiq do'kon joyi, restoran zonasi va ochiq amfiteatr rejalashtirilgan. Mintaqadagi yuqori turistlar oqimi savdo maydonlarini ijaraga berish talabini ta'minlaydi.",
    highlights: [
      "60+ do'kon joyi, restoran zonasi",
      "Turistik markazga 10 daqiqa piyoda masofada",
      "Ijara shartnomalari oldindan tuzilmoqda",
    ],
  },
  {
    slug: "buxoro-mehmonxona",
    title: "Buxoro mehmonxona loyihasi",
    city: "Buxoro",
    category: "hotel",
    lat: 39.7747,
    lng: 64.4286,
    target: 900_000_000,
    raised: 810_000_000,
    roi: "21%",
    durationMonths: 12,
    minInvestment: 20_000_000,
    investorsCount: 91,
    completionDate: "2026, III chorak",
    image:
      "https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&w=1200&q=80",
    description:
      "Buxoro eski shahar hududida 4-yulduzli, 48 xonali butik mehmonxona. Qurilish deyarli yakunlangan, hozirgi bosqich ichki jihozlash va sertifikatlash. Yuqori turistik faslgacha ishga tushirish rejalashtirilgan.",
    highlights: [
      "48 xonali, 4-yulduzli butik mehmonxona",
      "Qurilish 90% yakunlangan",
      "Yuqori mavsumga (bahor) ishga tushirish rejalashtirilgan",
    ],
  },
  {
    slug: "namangan-sanoat-majmuasi",
    title: "Namangan sanoat majmuasi",
    city: "Namangan",
    category: "industrial",
    lat: 40.9983,
    lng: 71.6726,
    target: 3_200_000_000,
    raised: 950_000_000,
    roi: "16%",
    durationMonths: 30,
    minInvestment: 40_000_000,
    investorsCount: 37,
    completionDate: "2028, I chorak",
    image:
      "https://images.unsplash.com/photo-1486325212027-8081e485255e?auto=format&fit=crop&w=1200&q=80",
    description:
      "To'qimachilik va qadoqlash uskunalari uchun ijaraga beriladigan zamonaviy sanoat ombor-sex majmuasi. Erkin iqtisodiy zonaga yaqinligi soliq imtiyozlarini beradi.",
    highlights: [
      "12,000 m² sanoat ombor-sex maydoni",
      "Erkin iqtisodiy zonaga yaqin",
      "Uzoq muddatli ijara shartnomalari muzokara qilinmoqda",
    ],
  },
  {
    slug: "xiva-turizm-majmuasi",
    title: "Xiva turizm majmuasi",
    city: "Xiva",
    category: "hotel",
    lat: 41.3775,
    lng: 60.3639,
    target: 1_100_000_000,
    raised: 300_000_000,
    roi: "19%",
    durationMonths: 20,
    minInvestment: 18_000_000,
    investorsCount: 24,
    completionDate: "2027, I chorak",
    image:
      "https://images.unsplash.com/photo-1497366216548-37526070297c?auto=format&fit=crop&w=1200&q=80",
    description:
      "Ichon-Qal'a devoriga yaqin an'anaviy uslubdagi mehmonxona va hunarmandchilik bozori majmuasi. Xorazm me'morchiligi uslubida qurilmoqda, mahalliy hunarmandlar bilan hamkorlik rejalashtirilgan.",
    highlights: [
      "An'anaviy Xorazm me'morchiligi uslubida",
      "Ichon-Qal'aga 5 daqiqa piyoda masofada",
      "Mahalliy hunarmandchilik bozori bilan integratsiya",
    ],
  },
  {
    slug: "andijon-turar-joy-majmuasi",
    title: "Andijon turar-joy majmuasi",
    city: "Andijon",
    category: "residential",
    lat: 40.7821,
    lng: 72.3442,
    target: 1_600_000_000,
    raised: 1_100_000_000,
    roi: "15%",
    durationMonths: 16,
    minInvestment: 12_000_000,
    investorsCount: 103,
    completionDate: "2026, II chorak",
    image:
      "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?auto=format&fit=crop&w=1200&q=80",
    description:
      "O'rta segment uchun mo'ljallangan 6 qavatli, 5 blokli turar-joy majmuasi. Qurilish faol bosqichda, birinchi blok ushbu yil oxirida topshiriladi.",
    highlights: [
      "5 blok, 6 qavat, 210 xonadon",
      "Birinchi blok shu yil oxirida topshiriladi",
      "Maktab va bog'cha hududi ichida rejalashtirilgan",
    ],
  },
];

export function formatUzsAmount(amount: number): string {
  return `${Math.round(amount).toLocaleString("uz-UZ")} so'm`;
}

export async function getInvestmentOpportunities(): Promise<InvestmentOpportunity[]> {
  return OPPORTUNITIES;
}

export async function getInvestmentOpportunity(
  slug: string,
): Promise<InvestmentOpportunity | null> {
  return OPPORTUNITIES.find((o) => o.slug === slug) ?? null;
}
