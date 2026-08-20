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
import { GlobalAdSidebars } from "@/components/site/GlobalAdSidebars";
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
  // An AdSlot sits between later sections, plus the two sticky sidebar slots
  // (`GlobalAdSidebars`, shared with `AppShell` so every page gets the same ones) in the side
  // gutters on very wide screens. The `relative` wrapper below is deliberately everything EXCEPT
  // `<Footer/>` -- see `GlobalAdSidebars`' own docstring for why that's what makes the sticky
  // sidebars stop at the footer instead of riding over it.
  return (
    <main className="min-h-screen overflow-x-hidden bg-background text-foreground">
      <div className="relative">
        <Navbar />
        <GlobalAdSidebars />

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
      </div>
      <Footer />
    </main>
  );
}
