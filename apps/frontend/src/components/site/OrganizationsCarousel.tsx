/**
 * Homepage "Tashkilotlar" widget -- one chip per `MainCategory` (the 6 fixed organization
 * sectors), styled exactly like `CategoryCarousel.tsx`'s own `CategoryPill` (same rounded-2xl
 * white-card image tile + bold label underneath, same fade-up-on-scroll motion), so the
 * "Tashkilotlar" section visually reads as a sibling of the "Kategoriyalar" rail right above it,
 * not a different widget. Each chip links to `/companies?category=<value>`, which pre-selects
 * that sector's tab on the real directory page. Deliberately NOT one card per business profile --
 * `MainCategory` is a fixed, admin-defined 6-value set (unlike catalog categories, which come
 * from the CMS), so a representative photo per sector is picked once here rather than sourced
 * per organization.
 */
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import { Link } from "@tanstack/react-router";
import { ArrowUpRight } from "lucide-react";
import {
  MAIN_CATEGORIES,
  MAIN_CATEGORY_LABEL,
  MAIN_CATEGORY_IMAGE,
  MAIN_CATEGORY_SLUG,
  type MainCategory,
} from "@/lib/business-profiles-client";

function CategoryChip({ category, index }: { category: MainCategory; index: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.35, delay: index * 0.05, ease: [0.22, 1, 0.36, 1] }}
    >
      <Link
        to="/organizations/$categorySlug"
        params={{ categorySlug: MAIN_CATEGORY_SLUG[category] }}
        className="group flex w-24 shrink-0 flex-col items-center gap-2.5 rounded-2xl border border-transparent px-2 py-3 text-center transition-all hover:border-border hover:bg-card hover:shadow-soft sm:w-28"
      >
        <div className="relative flex size-16 items-center justify-center overflow-hidden rounded-2xl border border-border bg-white shadow-soft transition-all duration-300 group-hover:-translate-y-0.5 group-hover:shadow-glow sm:size-20">
          <img
            src={MAIN_CATEGORY_IMAGE[category]}
            alt=""
            className="size-full object-cover"
            loading="lazy"
          />
        </div>
        <div className="font-display text-[12.5px] font-semibold leading-tight text-foreground/85 group-hover:text-foreground">
          {MAIN_CATEGORY_LABEL[category]}
        </div>
      </Link>
    </motion.div>
  );
}

export function OrganizationsCarousel() {
  const { t } = useTranslation();

  return (
    <section id="organizations" className="relative scroll-mt-24 px-6 py-16">
      <motion.div
        initial={{ opacity: 0, y: 24 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-80px" }}
        transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
        className="relative mx-auto max-w-6xl overflow-hidden rounded-[2rem] border border-border bg-card/60 px-6 py-14 shadow-elevated backdrop-blur-xl sm:px-10"
      >
        <div className="gradient-mesh absolute inset-0 opacity-25" aria-hidden />
        <div className="absolute inset-x-0 top-0 -z-0 h-1/2 bg-[radial-gradient(ellipse_at_top,oklch(0.75_0.16_275_/_0.14),transparent_70%)]" />

        <div className="relative text-center">
          <div className="inline-flex items-center gap-2 rounded-full border border-border bg-card/80 px-3 py-1 text-[11px] font-medium uppercase tracking-widest text-foreground/70 backdrop-blur">
            <span className="size-1.5 rounded-full bg-primary" />
            {t("organizations.eyebrow", { defaultValue: "Tasdiqlangan hamkorlar" })}
          </div>
          <h2 className="font-display mt-4 text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
            {t("organizations.title", { defaultValue: "Tashkilotlar" })}
          </h2>
          <p className="mx-auto mt-2 max-w-xl text-sm text-muted-foreground">
            {t("organizations.subtitle", {
              defaultValue:
                "Qurilish, agentlik, bank va xizmat sohasidagi tasdiqlangan tashkilotlar — bitta ekotizimda.",
            })}
          </p>

          <div className="mt-10 flex flex-wrap items-start justify-center gap-1">
            {MAIN_CATEGORIES.map((category, i) => (
              <CategoryChip key={category} category={category} index={i} />
            ))}
          </div>

          <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
            <Link
              to="/list"
              className="group inline-flex items-center gap-1.5 rounded-full bg-primary px-5 py-2.5 text-xs font-semibold text-primary-foreground shadow-soft transition hover:shadow-glow"
            >
              {t("organizations.cta", { defaultValue: "Hamkor sifatida qo'shiling" })}
              <ArrowUpRight className="size-3.5 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
            </Link>
          </div>
        </div>
      </motion.div>
    </section>
  );
}
