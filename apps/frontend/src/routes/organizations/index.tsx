/**
 * Bosqich 1 -- the "Tashkilotlar" hub: exactly 6 `MainCategory` cards, no organization listings
 * (those live one level down, per category, at `/organizations/$categorySlug`). Reachable from
 * the homepage `OrganizationsCarousel`'s "Barcha tashkilotlarni ko'rish" link and every
 * "Tashkilotlar" nav item (`Navbar`, `MobileMenu`, `AudienceSplit`).
 */
import { createFileRoute, Link } from "@tanstack/react-router";
import { motion } from "framer-motion";
import { ArrowUpRight } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { Container } from "@/components/layout/Container";
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
          <img
            src={MAIN_CATEGORY_IMAGE[category]}
            alt=""
            loading="lazy"
            className="size-full object-cover transition duration-500 group-hover:scale-105"
          />
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

function Page() {
  return (
    <AppShell>
      <PageHeader
        eyebrow="Tasdiqlangan hamkorlar"
        title="Tashkilotlar"
        description="Qurilish, moliya, ishlab chiqarish va xizmat ko'rsatish sohasidagi tashkilotlar — asosiy yo'nalishni tanlang."
        crumbs={[{ label: "Bosh sahifa", to: "/" }, { label: "Tashkilotlar" }]}
      />
      <Container wide className="py-10">
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {MAIN_CATEGORIES.map((category, i) => (
            <CategoryCard key={category} category={category} index={i} />
          ))}
        </div>
      </Container>
    </AppShell>
  );
}
