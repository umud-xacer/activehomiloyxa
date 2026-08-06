import { createFileRoute } from "@tanstack/react-router";
import "@/lib/i18n";
import { Navbar } from "@/components/site/Navbar";
import { Hero } from "@/components/site/Hero";
import { StatsBand } from "@/components/site/StatsBand";
import { BrandAbout } from "@/components/site/BrandAbout";
import { CategoryCarousel } from "@/components/site/CategoryCarousel";
import { FeaturedProperties } from "@/components/site/FeaturedProperties";
import { EcosystemGrid } from "@/components/site/EcosystemGrid";
import { PromoBanner } from "@/components/site/PromoBanner";
import { BannerSlot } from "@/components/site/BannerSlot";
import { MapPreview } from "@/components/site/MapPreview";
import { CtaBand } from "@/components/site/CtaBand";
import { Footer } from "@/components/site/Footer";

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
  return (
    <main className="relative min-h-screen overflow-hidden bg-background text-foreground">
      <Navbar />
      <Hero />
      <div className="mx-auto max-w-7xl px-6">
        <BannerSlot slotKey="homepage-hero" />
      </div>
      <StatsBand />
      <BrandAbout />
      <CategoryCarousel />
      <PromoBanner src="/information.jpg" alt="Uy ta'mirlash — Active Home" />
      <FeaturedProperties />
      <EcosystemGrid />
      <PromoBanner src="/information.jpg" alt="Uy ta'mirlash — Active Home" />
      <MapPreview />
      <PromoBanner src="/information.jpg" alt="Uy ta'mirlash — Active Home" />
      <CtaBand />
      <Footer />
    </main>
  );
}
