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
import { PromoBanner } from "@/components/site/PromoBanner";
import promoIpoteka from "@/assets/banners/promo-ipoteka.png";

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
  // AudienceSplit -> the promo banner -> Organizations -> Map -> the 12-process ecosystem ->
  // MissionBand -> the stats "proof strip" (its own section, below MissionBand) -> CTA/Footer.
  // An AdSlot sits between later sections, plus two fixed sidebar slots in the side gutters on
  // very wide screens.
  return (
    <main className="relative min-h-screen overflow-hidden bg-background text-foreground">
      <Navbar />

      <div className="pointer-events-none fixed inset-y-0 left-0 z-20 hidden w-[200px] justify-center pt-32 2xl:flex">
        <div className="pointer-events-auto sticky top-32">
          <AdSlot slotKey="HOMEPAGE_SIDEBAR_LEFT" variant="sidebar" />
        </div>
      </div>
      <div className="pointer-events-none fixed inset-y-0 right-0 z-20 hidden w-[200px] justify-center pt-32 2xl:flex">
        <div className="pointer-events-auto sticky top-32">
          <AdSlot slotKey="HOMEPAGE_SIDEBAR_RIGHT" variant="sidebar" />
        </div>
      </div>

      <Hero />
      <AudienceSplit />
      <PromoBanner src={promoIpoteka} alt="Orzuingizdagi uyni ipoteka orqali oling" />
      <OrganizationsCarousel />
      <AdSlot slotKey="HOMEPAGE_BANNER_1" />
      <MapPreview />
      <AdSlot slotKey="HOMEPAGE_BANNER_2" />
      <EcosystemGrid />
      <AdSlot slotKey="HOMEPAGE_BANNER_3" />
      <MissionBand />
      <PlatformStatsBand />
      <Footer />
    </main>
  );
}
