import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "@tanstack/react-router";
import { motion } from "framer-motion";
import { Sparkles, Search } from "lucide-react";
import worldMapBg from "@/assets/hero-bg-navy-map.jpg";
import { CategoryCarousel } from "./CategoryCarousel";
import { Container } from "@/components/layout/Container";
import { SearchResultsPanel } from "@/components/search/SearchResultsPanel";
import { AdSlot } from "./AdSlot";
import { useSkyscraperAdsEnabled } from "@/lib/use-skyscraper-ads-enabled";

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  show: (i = 0) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.8, delay: i * 0.08, ease: [0.22, 1, 0.36, 1] as const },
  }),
};

export function Hero() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState("");
  const skyscraperAdsEnabled = useSkyscraperAdsEnabled();

  function submitFullSearch() {
    const trimmed = query.trim();
    if (!trimmed) {
      setSearchOpen(true);
      return;
    }
    setSearchOpen(false);
    navigate({ to: "/search", search: { q: trimmed } });
  }

  return (
    <section className="hero-dark relative isolate overflow-hidden bg-background pt-28 pb-14 text-foreground md:pt-32 md:pb-16">
      <div
        className="absolute inset-0 -z-10 bg-cover bg-center"
        style={{ backgroundImage: `url(${worldMapBg})` }}
        aria-hidden
      />
      <div className="absolute inset-0 -z-10 bg-gradient-to-b from-background/70 via-background/25 to-background/85" />
      <div className="gradient-mesh absolute inset-0 -z-10" />
      <div className="absolute inset-x-0 top-0 -z-10 h-[50vh] bg-[radial-gradient(ellipse_at_top,oklch(0.75_0.16_275_/_0.25),transparent_60%)]" />

      {/* Ad columns sit INSIDE the hero band as real flex items (not absolute/fixed overlays),
          flush against its own left/right edges -- reserving their own width so the centered
          content can never collide with them, while the navy background above stays a true
          `w-full` edge-to-edge section (this row is the only thing that's width-constrained, not
          the section itself, so the background never shrinks to make room). Default OFF -- see
          `useSkyscraperAdsEnabled`'s own docstring; when disabled these two columns don't render
          at all, so the row collapses to a single centered column with no reserved gutter. */}
      <div className="relative flex items-start justify-center gap-4 px-3 sm:px-4">
        {skyscraperAdsEnabled && (
          <div className="hidden w-[160px] shrink-0 pt-24 xl:block">
            <AdSlot slotKey="HOMEPAGE_SIDEBAR_LEFT" variant="sidebar" />
          </div>
        )}

        <div className="min-w-0 flex-1">
          <Container>
            <motion.div
              initial="hidden"
              animate="show"
              variants={{ show: { transition: { staggerChildren: 0.07 } } }}
              className="mx-auto max-w-3xl text-center"
            >
              <motion.div
                variants={fadeUp}
                custom={0}
                className="inline-flex items-center gap-2 rounded-full border border-border bg-card/60 px-3 py-1 text-xs font-medium text-foreground/70 backdrop-blur"
              >
                <Sparkles className="size-3 text-primary" />
                {t("hero.eyebrow")}
              </motion.div>

              <motion.h1
                variants={fadeUp}
                custom={1}
                className="font-display text-hero mt-5 text-balance font-semibold tracking-tight text-foreground"
              >
                {t("hero.title").split(".")[0]}.
                <br />
                <span className="bg-gradient-to-r from-primary via-primary-glow to-accent bg-clip-text text-transparent">
                  {t("hero.title").split(".")[1] || ""}
                </span>
              </motion.h1>

              <motion.p
                variants={fadeUp}
                custom={2}
                className="mx-auto mt-4 max-w-xl text-balance text-sm text-muted-foreground sm:text-base"
              >
                {t("hero.subtitle")}
              </motion.p>

              {/* Search */}
              <motion.div variants={fadeUp} custom={3} className="mx-auto mt-7 max-w-2xl">
                <div className="group relative">
                  <div className="absolute -inset-px rounded-2xl bg-gradient-to-r from-primary/30 via-primary-glow/40 to-accent/30 opacity-60 blur-md transition group-focus-within:opacity-100" />
                  <div className="relative flex items-center gap-2 rounded-2xl border border-border bg-card/90 p-2 shadow-elevated backdrop-blur-xl">
                    <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
                      <Search className="size-4" />
                    </div>
                    <input
                      type="text"
                      value={query}
                      onChange={(e) => {
                        setQuery(e.target.value);
                        setSearchOpen(true);
                      }}
                      onFocus={() => setSearchOpen(true)}
                      onKeyDown={(e) => e.key === "Enter" && submitFullSearch()}
                      placeholder={t("hero.search_placeholder")}
                      className="min-w-0 flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground/80 focus:outline-none sm:text-[15px]"
                    />
                    <span className="hidden items-center gap-1 rounded-full bg-primary/8 px-2.5 py-1 text-[11px] font-semibold text-primary sm:inline-flex">
                      <Sparkles className="size-3" />
                      {t("hero.ai_hint")}
                    </span>
                    <button
                      type="button"
                      onClick={submitFullSearch}
                      className="inline-flex items-center gap-1 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition hover:shadow-glow"
                    >
                      {t("hero.search_button")}
                    </button>
                  </div>
                  {/* Controlled mode -- this input above IS the search box, so the dropdown renders
                  results only, seamlessly attached right under it (no second embedded input). */}
                  <SearchResultsPanel
                    open={searchOpen}
                    onOpenChange={setSearchOpen}
                    externalQuery={query}
                    onExternalQueryChange={setQuery}
                    className="absolute inset-x-0 top-full z-50 mt-2 overflow-hidden rounded-2xl border border-slate-100 bg-card text-left shadow-xl"
                  />
                </div>
              </motion.div>
            </motion.div>
          </Container>

          {/* Categories live inside Hero's own dark band -- continues the same navy gradient
              rather than handing off to a separate white section right below the search box. */}
          <CategoryCarousel />
        </div>

        {skyscraperAdsEnabled && (
          <div className="hidden w-[160px] shrink-0 pt-24 xl:block">
            <AdSlot slotKey="HOMEPAGE_SIDEBAR_RIGHT" variant="sidebar" />
          </div>
        )}
      </div>
    </section>
  );
}
