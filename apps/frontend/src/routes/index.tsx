import { createFileRoute } from "@tanstack/react-router";
import "@/lib/i18n";
import { Navbar } from "@/components/site/Navbar";
import { Hero } from "@/components/site/Hero";
import { AudienceSplit } from "@/components/site/AudienceSplit";
import { CategoryCarousel } from "@/components/site/CategoryCarousel";
import { EcosystemGrid } from "@/components/site/EcosystemGrid";
import { OrganizationsCarousel } from "@/components/site/OrganizationsCarousel";
import { MapPreview } from "@/components/site/MapPreview";
import { MissionBand } from "@/components/site/MissionBand";
import { Footer } from "@/components/site/Footer";
import { AdSlot } from "@/components/site/AdSlot";
import { PromoBanner } from "@/components/site/PromoBanner";
import promoUyTamirlash from "@/assets/banners/promo-uy-tamirlash.jpg";

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
      { property: "og:url", content: "https://active-home.lovable.app/" },
    ],
    links: [{ rel: "canonical", href: "https://active-home.lovable.app/" }],
  }),
  component: Index,
});

function Index() {
  // Order: Navbar -> Hero (search stays on top) -> Categories (immediately below the search, no
  // ad banner interrupting, so they're usable right after a search) -> the promo banner ->
  // Organizations (premium panel, took over Categories' old slot) -> Map -> the 12-process
  // ecosystem -> CTA/Footer. An AdSlot sits between later sections, plus two fixed sidebar slots
  // in the side gutters on very wide screens.
  return (
    <main className="relative min-h-screen overflow-hidden bg-background text-foreground">
      <Navbar />

      <div className="pointer-events-none fixed inset-y-0 left-0 z-20 hidden w-[200px] justify-center pt-32 2xl:flex">
        <div className="pointer-events-auto sticky top-32">
          <AdSlot variant="sidebar" />
        </div>
      </div>
      <div className="pointer-events-none fixed inset-y-0 right-0 z-20 hidden w-[200px] justify-center pt-32 2xl:flex">
        <div className="pointer-events-auto sticky top-32">
          <AdSlot variant="sidebar" />
        </div>
      </div>

      <Hero />
      <AudienceSplit />
      <CategoryCarousel />
      <PromoBanner
        src={promoUyTamirlash}
        alt="Uy ta'mirlash bosh og'riq emas!"
        aspect="aspect-[16/5]"
      />
      <OrganizationsCarousel />
      <AdSlot />
      <MapPreview />
      <AdSlot />
      <EcosystemGrid />
      <AdSlot />
      <MissionBand />
      <Footer />
    </main>
  );
}
