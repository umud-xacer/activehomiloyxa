import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import { Link } from "@tanstack/react-router";
import { Heart, MapPin, BedDouble, Bath, Square, Sparkles, ArrowRight } from "lucide-react";
import { Container } from "@/components/layout/Container";

type Prop = {
  title: string;
  city: string;
  price: string;
  beds: number;
  baths: number;
  sqft: number;
  score: number;
  bg: string;
  tag?: string;
};

const PROPS: Prop[] = [
  {
    title: "Skyline Penthouse",
    city: "Dubai · Marina",
    price: "$1,240,000",
    beds: 4,
    baths: 3,
    sqft: 320,
    score: 96,
    bg: "linear-gradient(135deg,#1e293b,#334155 60%,#475569)",
    tag: "New",
  },
  {
    title: "Garden Cottage",
    city: "Tashkent · Yunusabad",
    price: "$184,500",
    beds: 3,
    baths: 2,
    sqft: 145,
    score: 92,
    bg: "linear-gradient(135deg,#064e3b,#0d7a5f 60%,#34d399)",
  },
  {
    title: "Lakeside Villa",
    city: "Como · Italy",
    price: "$3,890,000",
    beds: 6,
    baths: 5,
    sqft: 540,
    score: 99,
    bg: "linear-gradient(135deg,#0c2340,#1a4a6e 60%,#5cbdb9)",
    tag: "Featured",
  },
];

export function FeaturedProperties() {
  const { t } = useTranslation();
  return (
    <section className="py-24">
      <Container>
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div className="max-w-xl">
            <h2 className="font-display text-3xl font-semibold tracking-tight text-foreground sm:text-4xl md:text-5xl">
              {t("featured.title")}
            </h2>
            <p className="mt-3 text-base text-muted-foreground">{t("featured.subtitle")}</p>
          </div>
          <Link
            to="/properties"
            className="group inline-flex items-center gap-1 text-sm font-semibold text-primary"
          >
            {t("featured.view_all")}
            <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
          </Link>
        </div>

        <div className="mt-12 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {PROPS.map((p, i) => (
            <motion.article
              key={p.title}
              initial={{ opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-80px" }}
              transition={{ duration: 0.7, delay: i * 0.1, ease: [0.22, 1, 0.36, 1] }}
              whileHover={{ y: -6 }}
              className="group relative overflow-hidden rounded-3xl border border-border bg-card shadow-soft transition-shadow hover:shadow-elevated"
            >
              {/* Image */}
              <div className="relative h-64 overflow-hidden">
                <div
                  className="absolute inset-0 transition-transform duration-700 group-hover:scale-105"
                  style={{ background: p.bg }}
                />
                <div className="absolute inset-0 bg-gradient-to-t from-black/40 via-transparent to-transparent" />
                {/* Top badges */}
                <div className="absolute inset-x-4 top-4 flex items-start justify-between">
                  <div className="flex gap-2">
                    {p.tag && (
                      <span className="rounded-full bg-white/90 px-2.5 py-1 text-[11px] font-semibold text-foreground backdrop-blur">
                        {p.tag}
                      </span>
                    )}
                    <span className="inline-flex items-center gap-1 rounded-full bg-primary/90 px-2.5 py-1 text-[11px] font-semibold text-primary-foreground backdrop-blur">
                      <Sparkles className="size-3" /> AI {p.score}
                    </span>
                  </div>
                  <button
                    aria-label="Save"
                    className="flex size-9 items-center justify-center rounded-full bg-white/90 text-foreground/80 backdrop-blur transition hover:bg-white hover:text-destructive"
                  >
                    <Heart className="size-4" />
                  </button>
                </div>
              </div>

              {/* Body */}
              <div className="p-5">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h3 className="font-display text-lg font-semibold text-foreground">
                      {p.title}
                    </h3>
                    <div className="mt-1 inline-flex items-center gap-1 text-xs text-muted-foreground">
                      <MapPin className="size-3" /> {p.city}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-display text-lg font-semibold text-foreground">
                      {p.price}
                    </div>
                  </div>
                </div>

                <div className="mt-4 flex items-center gap-4 border-t border-border pt-4 text-xs text-muted-foreground">
                  <span className="inline-flex items-center gap-1.5">
                    <BedDouble className="size-3.5" />
                    {p.beds} beds
                  </span>
                  <span className="inline-flex items-center gap-1.5">
                    <Bath className="size-3.5" />
                    {p.baths} baths
                  </span>
                  <span className="inline-flex items-center gap-1.5">
                    <Square className="size-3.5" />
                    {p.sqft} m²
                  </span>
                </div>
              </div>
            </motion.article>
          ))}
        </div>
      </Container>
    </section>
  );
}
