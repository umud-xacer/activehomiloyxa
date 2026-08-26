/**
 * Bosqich 1 -- the "Tashkilotlar" hub: exactly 6 `MainCategory` cards, no organization listings
 * (those live one level down, per category, at `/organizations/$categorySlug`). Reachable from
 * the homepage `OrganizationsCarousel`'s "Barcha tashkilotlarni ko'rish" link and every
 * "Tashkilotlar" nav item (`Navbar`, `MobileMenu`, `AudienceSplit`).
 */
import { createFileRoute, Link } from "@tanstack/react-router";
import { motion } from "framer-motion";
import { useState } from "react";
import { ArrowUpRight } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { Container } from "@/components/layout/Container";
import { AdSlot } from "@/components/site/AdSlot";
import {
  MAIN_CATEGORIES,
  MAIN_CATEGORY_LABEL,
  MAIN_CATEGORY_DESCRIPTION,
  MAIN_CATEGORY_IMAGE,
  MAIN_CATEGORY_ACCENT,
  MAIN_CATEGORY_SLUG,
  type MainCategory,
} from "@/lib/business-profiles-client";

export const Route = createFileRoute("/organizations/")({
  head: () => ({
    meta: [
      { title: "Tashkilotlar — ActiveHome" },
      {
        name: "description",
        content: "ActiveHome'dagi tasdiqlangan tashkilotlar — asosiy yo'nalish bo'yicha.",
      },
    ],
  }),
  component: Page,
});

function CategoryCard({ category, index }: { category: MainCategory; index: number }) {
  // Same "the URL is well-formed but the keyless third-party photo source can still fail at
  // request time" defensive fallback `SubCategoryCard` (one level down) uses.
  const [imgFailed, setImgFailed] = useState(false);
  const accent = MAIN_CATEGORY_ACCENT[category];

  return (
    <motion.div
      initial={{ opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.4, delay: Math.min(index * 0.06, 0.4), ease: [0.22, 1, 0.36, 1] }}
    >
      <Link
        to="/organizations/$categorySlug"
        params={{ categorySlug: MAIN_CATEGORY_SLUG[category] }}
        className="group flex h-full flex-col overflow-hidden rounded-3xl border border-border bg-card shadow-soft transition-all duration-300 hover:-translate-y-1 hover:shadow-elevated"
      >
        <div className="relative h-40 overflow-hidden sm:h-44">
          {imgFailed ? (
            <div
              className="size-full"
              style={{ background: `linear-gradient(135deg, ${accent}55 0%, ${accent}14 100%)` }}
            />
          ) : (
            <img
              src={MAIN_CATEGORY_IMAGE[category]}
              alt=""
              loading="lazy"
              onError={() => setImgFailed(true)}
              className="size-full object-cover transition duration-500 group-hover:scale-105"
            />
          )}
          <div className="absolute inset-0 bg-gradient-to-t from-black/65 via-black/5 to-transparent" />
        </div>
        <div className="flex flex-1 flex-col gap-1.5 p-5">
          <h3 className="font-display text-base font-semibold text-foreground sm:text-lg">
            {MAIN_CATEGORY_LABEL[category]}
          </h3>
          <p className="text-sm text-muted-foreground">{MAIN_CATEGORY_DESCRIPTION[category]}</p>
          <span
            className="mt-3 inline-flex items-center gap-1.5 text-xs font-semibold"
            style={{ color: MAIN_CATEGORY_ACCENT[category] }}
          >
            Ko'rish
            <ArrowUpRight className="size-3.5 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
          </span>
        </div>
      </Link>
    </motion.div>
  );
}

/** Mobile-only (`sm:hidden`) compact tile for the same 10 sectors -- a full-width vertical stack
 * of `CategoryCard`s (each ~250px tall with its photo) made the page scroll for several thousand
 * pixels just to see every sector, confirmed as a real complaint from a live mobile screenshot.
 * Reuses `CategoryCarousel.tsx`'s own established "circular photo + short label" rail pattern
 * (same site already has that exact interaction for regular categories) rather than inventing a
 * new one, just with a round avatar instead of that component's rounded-square tile per this
 * task's own ask. */
function CompactCategoryTile({ category, index }: { category: MainCategory; index: number }) {
  const [imgFailed, setImgFailed] = useState(false);
  const accent = MAIN_CATEGORY_ACCENT[category];

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ duration: 0.3, delay: Math.min(index * 0.03, 0.3), ease: [0.22, 1, 0.36, 1] }}
      className="snap-start"
    >
      <Link
        to="/organizations/$categorySlug"
        params={{ categorySlug: MAIN_CATEGORY_SLUG[category] }}
        className="flex w-[76px] flex-col items-center gap-1.5 text-center"
      >
        <div className="relative size-14 shrink-0 overflow-hidden rounded-full border border-border shadow-soft">
          {imgFailed ? (
            <div
              className="size-full"
              style={{ background: `linear-gradient(135deg, ${accent}55 0%, ${accent}14 100%)` }}
            />
          ) : (
            <img
              src={MAIN_CATEGORY_IMAGE[category]}
              alt=""
              loading="lazy"
              onError={() => setImgFailed(true)}
              className="size-full object-cover"
            />
          )}
        </div>
        <span className="line-clamp-2 text-[11px] font-medium leading-tight text-foreground/85">
          {MAIN_CATEGORY_LABEL[category]}
        </span>
      </Link>
    </motion.div>
  );
}

function Page() {
  return (
    <AppShell>
      <PageHeader
        eyebrow="Tasdiqlangan hamkorlar"
        title="Tashkilotlar"
        description="Qurilish, moliya, ishlab chiqarish va xizmat ko'rsatish sohasidagi tashkilotlar — asosiy yo'nalishni tanlang."
        crumbs={[{ label: "Bosh sahifa", to: "/" }, { label: "Tashkilotlar" }]}
      />
      <Container wide className="py-8 sm:py-10">
        {/* Below `sm:` a 2-row horizontal snap carousel (OLX/Instagram-highlights style) instead
            of the vertical photo-card stack -- see `CompactCategoryTile`'s own doc comment. */}
        <div className="-mx-4 overflow-x-auto px-4 pb-1 scrollbar-none sm:hidden">
          <div className="grid auto-cols-max grid-flow-col grid-rows-2 gap-x-3 gap-y-3 snap-x snap-mandatory">
            {MAIN_CATEGORIES.map((category, i) => (
              <CompactCategoryTile key={category} category={category} index={i} />
            ))}
          </div>
        </div>
        <div className="hidden gap-5 sm:grid sm:grid-cols-2 lg:grid-cols-3">
          {MAIN_CATEGORIES.map((category, i) => (
            <CategoryCard key={category} category={category} index={i} />
          ))}
        </div>
      </Container>

      <div className="pb-10">
        <AdSlot slotKey="ORGANIZATIONS_BANNER_CAROUSEL" variant="carousel" />
      </div>
    </AppShell>
  );
}
