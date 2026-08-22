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
  // An AdSlot sits between later sections, plus the two sticky sidebar slots
  // (`GlobalAdSidebars`, shared with `AppShell` so every page gets the same ones) in the side
  // gutters on very wide screens. The `relative` wrapper below is deliberately everything EXCEPT
  // `<Footer/>` -- see `GlobalAdSidebars`' own docstring for why that's what makes the sticky
  // sidebars stop at the footer instead of riding over it.
  // No `overflow-x-hidden` here (nor anywhere else up this tree) -- setting overflow on EITHER
  // axis forces the other to compute to `auto` per spec, which makes the browser treat this
  // element as a scroll container for `position: sticky` purposes even though it never actually
  // gets its own internal scrollbar (nothing constrains its height). Confirmed live: with it
  // present, GlobalAdSidebars' sticky child stopped sticking entirely -- it just scrolled
  // normally with the page instead of pinning near the viewport top.
  return (
    <main className="min-h-screen bg-background text-foreground">
      {/* `2xl:grid-cols-[200px_minmax(0,1fr)_200px]` reserves real column space for the sidebar
       * ad slots instead of overlaying them -- see GlobalAdSidebars.tsx for why. */}
      <div className="relative grid grid-cols-1 2xl:grid-cols-[200px_minmax(0,1fr)_200px]">
        <Navbar />
        <GlobalAdSidebars />

        <div className="min-w-0 col-start-1 row-start-1 2xl:col-start-2">
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
      </div>
      <Footer />
    </main>
  );
}
