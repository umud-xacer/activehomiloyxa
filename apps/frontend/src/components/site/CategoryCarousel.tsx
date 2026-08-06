/**
 * Categories -- an Airbnb-style horizontal icon rail: compact, scannable at a glance, and takes
 * far less vertical space than a description-card grid (previously a static grid of 12 cards with
 * a paragraph each; before that, an infinite auto-scrolling marquee).
 *
 * Wired to the real `/categories` endpoint (admin-managed via the Configuration module's
 * category-versioning workflow -- whatever an admin publishes there shows up here). `CATS` below
 * is the offline/empty-backend fallback: the real 17-category taxonomy and icon artwork from the
 * platform's original Django build (`ActiveReturn`), carried over so the fallback still looks like
 * the real product rather than a generic placeholder set. `ICON_BY_PATH` reuses those same icons
 * for the 3 categories currently seeded in the new backend; anything else gets a generic icon and
 * links to `/categories/$slug`.
 */
import { useRef, useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import { Link } from "@tanstack/react-router";
import { ChevronLeft, ChevronRight, Tag, type LucideIcon } from "lucide-react";
import { catalogClient, type CategorySummary } from "@/lib/catalog-client";

import iconKopQavatli from "@/assets/categories/Artboard_1_rtGKuRl.png";
import iconKotej from "@/assets/categories/Artboard_1_copy_2_2QY3FEr.png";
import iconHovli from "@/assets/categories/Artboard_1_copy_4_gWZUOyb.png";
import iconNoturar from "@/assets/categories/Artboard_1_copy_21_PP9zTlD.png";
import iconDalaHovli from "@/assets/categories/Artboard_1_copy_5.png";
import iconBoshYer from "@/assets/categories/Artboard_1_copy_3.png";
import iconXizmat from "@/assets/categories/Artboard_1_copy_11.png";
import iconIshOrni from "@/assets/categories/Artboard_1_copy_10_3.png";
import iconQurilishMollari from "@/assets/categories/Artboard_1_copy_24.png";
import iconMebelMollari from "@/assets/categories/Artboard_1_copy_14.png";
import iconMaishiyTexnika from "@/assets/categories/Artboard_1_copy_15_QoxosFS.png";
import iconUyBezaklari from "@/assets/categories/Artboard_1_copy_16_4oA3op9.png";
import iconLandshaft from "@/assets/categories/Artboard_1_copy_17_M5upZcK.png";
import iconUniforma from "@/assets/categories/Artboard_1_copy_18_JmQ8b7A.png";
import iconMebelSalon from "@/assets/categories/Artboard_1_copy_19_XG9yRiO.png";
import iconHostel from "@/assets/categories/Hostel.png";
import iconMexmonxona from "@/assets/categories/Hotel.png";

type Cat = {
  key: string;
  image?: string;
  Icon?: LucideIcon;
  to: string;
  label?: string;
};

/** The real ActiveHome taxonomy (17 top-level categories), carried over verbatim from the
 * platform's original build so the fallback content is the genuine product, not a placeholder.
 * Every category -- real-estate or not -- opens its own `/categories/$slug` page (listings +
 * map, both scoped to that one category); there is no per-category destination override anymore. */
const CATS: Cat[] = [
  {
    key: "kop-qavatli-binolar",
    image: iconKopQavatli,
    to: "/categories/kop-qavatli-binolar",
    label: "Ko'p qavatli binolar",
  },
  { key: "kotejlar", image: iconKotej, to: "/categories/kotejlar", label: "Kotejlar" },
  { key: "hovlilar", image: iconHovli, to: "/categories/hovlilar", label: "Hovlilar" },
  {
    key: "noturar-binolar",
    image: iconNoturar,
    to: "/categories/noturar-binolar",
    label: "Noturar binolar",
  },
  {
    key: "dala-hovlilar",
    image: iconDalaHovli,
    to: "/categories/dala-hovlilar",
    label: "Dala hovlilar",
  },
  { key: "bosh-yerlar", image: iconBoshYer, to: "/categories/bosh-yerlar", label: "Bo'sh yerlar" },
  {
    key: "xizmat-korsatish",
    image: iconXizmat,
    to: "/categories/xizmat-korsatish",
    label: "Xizmat ko'rsatish",
  },
  { key: "ish-orni", image: iconIshOrni, to: "/categories/ish-orni", label: "Ish o'rni" },
  {
    key: "qurilish-materiallari",
    image: iconQurilishMollari,
    to: "/categories/qurilish-materiallari",
    label: "Qurilish materiallari",
  },
  {
    key: "mebel-materiallari",
    image: iconMebelMollari,
    to: "/categories/mebel-materiallari",
    label: "Mebel materiallari",
  },
  {
    key: "maishiy-texnikalar",
    image: iconMaishiyTexnika,
    to: "/categories/maishiy-texnikalar",
    label: "Maishiy texnikalar",
  },
  {
    key: "uy-bezaklari",
    image: iconUyBezaklari,
    to: "/categories/uy-bezaklari",
    label: "Uy bezaklari",
  },
  {
    key: "landshaft-dizayni",
    image: iconLandshaft,
    to: "/categories/landshaft-dizayni",
    label: "Landshaft dizayni",
  },
  {
    key: "uniforma",
    image: iconUniforma,
    to: "/categories/uniforma-va-maxsus-kiyimlar",
    label: "Uniforma va maxsus kiyimlar",
  },
  {
    key: "mebel-salonlari",
    image: iconMebelSalon,
    to: "/categories/mebel-salonlari",
    label: "Mebel salonlari",
  },
  { key: "hostel", image: iconHostel, to: "/categories/hostel", label: "Hostel" },
  { key: "mexmonxona", image: iconMexmonxona, to: "/categories/mexmonxona", label: "Mexmonxona" },
];

const ICON_BY_PATH: Record<string, string> = {
  "/kop-qavatli-binolar": iconKopQavatli,
  "/kotejlar": iconKotej,
  "/hovlilar": iconHovli,
  "/noturar-binolar": iconNoturar,
  "/dala-hovlilar": iconDalaHovli,
  "/bosh-yerlar": iconBoshYer,
  "/xizmat-korsatish": iconXizmat,
  "/ish-orni": iconIshOrni,
  "/chakana-savdo": iconQurilishMollari,
  "/mebel-materiallari": iconMebelMollari,
  "/maishiy-texnikalar": iconMaishiyTexnika,
  "/uy-bezaklari": iconUyBezaklari,
  "/landshaft-dizayni": iconLandshaft,
  "/uniforma-va-maxsus-kiyimlar": iconUniforma,
  "/mebel-salonlari": iconMebelSalon,
  "/hostel": iconHostel,
  "/mexmonxona": iconMexmonxona,
};

export function categoryLabel(name: Record<string, string>, lang: string): string {
  return (
    name[lang === "uz" ? "uz_latn" : lang] ??
    name.uz_latn ??
    name.en ??
    Object.values(name)[0] ??
    ""
  );
}

function apiCategoryToCat(cat: CategorySummary, lang: string): Cat {
  const image = cat.iconUrl || ICON_BY_PATH[cat.path];
  return {
    key: cat.id,
    image,
    Icon: image ? undefined : Tag,
    to: `/categories/${cat.path.replace(/^\//, "")}`,
    label: categoryLabel(cat.name, lang),
  };
}

function CategoryPill({ cat, index }: { cat: Cat; index: number }) {
  const { t } = useTranslation();
  const Icon = cat.Icon;
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.35, delay: index * 0.025, ease: [0.22, 1, 0.36, 1] }}
      className="snap-start"
    >
      <Link
        to={cat.to}
        className="group flex w-24 shrink-0 flex-col items-center gap-2.5 rounded-2xl border border-transparent px-2 py-3 text-center transition-all hover:border-border hover:bg-card hover:shadow-soft sm:w-28"
      >
        <div className="flex size-16 items-center justify-center rounded-2xl bg-card-foreground/5 p-1.5 transition-transform group-hover:-translate-y-0.5 group-hover:scale-105 sm:size-20">
          {cat.image ? (
            <img src={cat.image} alt="" className="size-full object-contain" />
          ) : Icon ? (
            <Icon className="size-5 text-muted-foreground sm:size-[22px]" />
          ) : null}
        </div>
        <div className="font-display text-[12.5px] font-semibold leading-tight text-foreground/85 group-hover:text-foreground">
          {cat.label ?? t(`categories.${cat.key}`)}
        </div>
      </Link>
    </motion.div>
  );
}

export function CategoryCarousel() {
  const { i18n } = useTranslation();
  const railRef = useRef<HTMLDivElement>(null);
  const [canLeft, setCanLeft] = useState(false);
  const [canRight, setCanRight] = useState(true);
  const [apiCats, setApiCats] = useState<CategorySummary[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    catalogClient
      .listCategories()
      .then((cats) => {
        const topLevel = cats.filter((c) => c.status === "ACTIVE" && c.parentId === null);
        if (!cancelled && topLevel.length > 0) setApiCats(topLevel);
      })
      .catch(() => {
        /* backend unavailable -- fall back to the local fixture below */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const cats: Cat[] = apiCats ? apiCats.map((c) => apiCategoryToCat(c, i18n.language)) : CATS;

  const updateArrows = () => {
    const el = railRef.current;
    if (!el) return;
    setCanLeft(el.scrollLeft > 4);
    setCanRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 4);
  };

  useEffect(() => {
    updateArrows();
  }, [cats.length]);

  const scrollBy = (dir: 1 | -1) => {
    railRef.current?.scrollBy({ left: dir * 320, behavior: "smooth" });
  };

  return (
    <section className="relative py-14">
      <div className="mx-auto max-w-7xl px-6">
        <div className="flex items-center justify-end gap-4">
          {/* Desktop scroll arrows -- mobile relies on native swipe */}
          <div className="hidden items-center gap-2 sm:flex">
            <button
              type="button"
              onClick={() => scrollBy(-1)}
              disabled={!canLeft}
              aria-label="Scroll categories left"
              className="flex size-9 items-center justify-center rounded-full border border-border bg-card text-foreground/70 transition hover:border-primary/40 hover:text-foreground disabled:opacity-30"
            >
              <ChevronLeft className="size-4" />
            </button>
            <button
              type="button"
              onClick={() => scrollBy(1)}
              disabled={!canRight}
              aria-label="Scroll categories right"
              className="flex size-9 items-center justify-center rounded-full border border-border bg-card text-foreground/70 transition hover:border-primary/40 hover:text-foreground disabled:opacity-30"
            >
              <ChevronRight className="size-4" />
            </button>
          </div>
        </div>

        <div className="relative mt-6">
          {/* Edge fade masks hint that the rail scrolls */}
          <div className="pointer-events-none absolute inset-y-0 left-0 z-10 w-8 bg-gradient-to-r from-background to-transparent sm:w-14" />
          <div className="pointer-events-none absolute inset-y-0 right-0 z-10 w-8 bg-gradient-to-l from-background to-transparent sm:w-14" />
          <div
            ref={railRef}
            onScroll={updateArrows}
            className="scrollbar-none flex snap-x gap-1 overflow-x-auto scroll-smooth px-1 py-1"
          >
            {cats.map((c, i) => (
              <CategoryPill key={c.key} cat={c} index={i} />
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
