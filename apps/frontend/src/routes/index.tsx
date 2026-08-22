import { createFileRoute } from "@tanstack/react-router";
import "@/lib/i18n";
import { Navbar } from "@/components/site/Navbar";
import { Hero } from "@/components/site/Hero";
import { AudienceSplit } from "@/components/site/AudienceSplit";
import { EcosystemGrid } from "@/components/site/EcosystemGrid";
import { OrganizationsCarousel } from "@/components/site/OrganizationsCarousel";
import { MapPreview } from "@/components/site/MapPreview";
import { MissionBand } from "@/components/site/MissionBand";
import { PlatformStatsBand } from "@/components/site/PlatformStatsBand";
import { Footer } from "@/components/site/Footer";
import { AdSlot } from "@/components/site/AdSlot";
import { PromoCarousel, type PromoSlide } from "@/components/site/PromoCarousel";
import promoIpoteka from "@/assets/banners/promo-ipoteka.png";
import promoUyTamirlash from "@/assets/banners/promo-uy-tamirlash.png";

const PROMO_SLIDES: PromoSlide[] = [
  {
    src: promoIpoteka,
    alt: "Orzuingizdagi uyni ipoteka orqali oling",
    href: "tel:+998555000406",
    fit: "cover",
  },
  {
    src: promoUyTamirlash,
    alt: "Uy ta'mirlash bosh og'riq emas — mutaxassislarga qo'ng'iroq qiling",
    href: "tel:+998555000406",
    fit: "contain",
  },
];

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "ActiveHome — The home & building super app" },
      {
        name: "description",
        content:
          "Buy, rent, build, furnish and book — one AI-powered ecosystem for everything related to homes and buildings, worldwide.",
      },
      { property: "og:title", content: "ActiveHome — The home & building super app" },
      {
        property: "og:description",
        content:
          "Properties, hotels, construction, materials, furniture, design and services. One global platform.",
      },
      { property: "og:url", content: "https://activehome.uz/" },
    ],
    links: [{ rel: "canonical", href: "https://activehome.uz/" }],
  }),
  component: Index,
});

function Index() {
  // Order: Navbar -> Hero (search + Categories both live inside Hero's own dark band now, so
  // there's no separate white "categories" section handing off from the search box) ->
  // AudienceSplit -> the promo carousel -> Organizations -> Map -> the 12-process ecosystem ->
  // MissionBand -> the stats "proof strip" (its own section, below MissionBand) -> CTA/Footer.
  // An AdSlot sits between later sections. The two sidebar ad slots
  // (HOMEPAGE_SIDEBAR_LEFT/RIGHT) live INSIDE Hero itself now, not here -- see Hero.tsx. They
  // used to be a page-spanning sticky overlay (`GlobalAdSidebars`), but that meant reserving a
  // column for them across the ENTIRE page, which shrank every section's own full-bleed
  // background (Hero's navy band included) to make room. Scoping them to Hero keeps Hero's
  // background a true `w-full` edge-to-edge section while still making overlap with its content
  // impossible (real flex-reserved width, not an overlay) -- see Hero.tsx's own comment.
  return (
    <main className="min-h-screen bg-background text-foreground">
      <div className="relative">
        <Navbar />

        <Hero />
        <AudienceSplit />
        <PromoCarousel slides={PROMO_SLIDES} />
        <OrganizationsCarousel />
        <AdSlot slotKey="HOMEPAGE_BANNER_1" />
        <MapPreview />
        <AdSlot slotKey="HOMEPAGE_BANNER_2" />
        <EcosystemGrid />
        <AdSlot slotKey="HOMEPAGE_BANNER_3" />
        <MissionBand />
        <PlatformStatsBand />
      </div>
      <Footer />
    </main>
  );
}
