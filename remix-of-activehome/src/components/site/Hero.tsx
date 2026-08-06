import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import { useNavigate } from "@tanstack/react-router";
import { Sparkles, Search, MapPin, Building2, BedDouble, Hammer } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { searchApi, type Suggestion } from "@/lib/search-api";

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
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (query.trim().length < 2) {
      setSuggestions([]);
      return;
    }
    const timeout = setTimeout(() => {
      searchApi
        .suggest(query.trim())
        .then((results) => {
          setSuggestions(results);
          setOpen(true);
        })
        .catch(() => setSuggestions([]));
    }, 250);
    return () => clearTimeout(timeout);
  }, [query]);

  useEffect(() => {
    const onClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  const runSearch = (q: string) => {
    setOpen(false);
    navigate({ to: "/properties", search: { q } as never });
  };

  return (
    <section className="relative isolate overflow-hidden pt-36 pb-24 md:pt-44 md:pb-32">
      {/* World map background */}
      <div
        className="absolute inset-0 -z-10 bg-cover bg-center"
        style={{ backgroundImage: `url(/background.jpg)` }}
        aria-hidden
      />
      {/* Subtle light overlay for text readability */}
      <div className="absolute inset-0 -z-10 bg-gradient-to-b from-background/60 via-background/30 to-background/60" />
      {/* Mesh background */}
      <div className="gradient-mesh absolute inset-0 -z-10" />
      <div className="absolute inset-x-0 top-0 -z-10 h-[60vh] bg-[radial-gradient(ellipse_at_top,oklch(0.55_0.18_275_/_0.18),transparent_60%)]" />
      {/* Grid pattern */}
      <div
        className="absolute inset-0 -z-10 opacity-[0.04] [background-image:linear-gradient(to_right,currentColor_1px,transparent_1px),linear-gradient(to_bottom,currentColor_1px,transparent_1px)] [background-size:48px_48px]"
        aria-hidden
      />

      <div className="mx-auto max-w-7xl px-6">
        <motion.div
          initial="hidden"
          animate="show"
          variants={{ show: { transition: { staggerChildren: 0.08 } } }}
          className="mx-auto max-w-4xl text-center"
        >
          <motion.div variants={fadeUp} custom={0} className="inline-flex items-center gap-2 rounded-full border border-border bg-card/60 px-3 py-1 text-xs font-medium text-foreground/70 backdrop-blur">
            <Sparkles className="size-3 text-primary" />
            {t("hero.eyebrow")}
          </motion.div>

          <motion.h1
            variants={fadeUp}
            custom={1}
            className="font-display mt-6 text-balance text-5xl font-semibold leading-[1.05] tracking-tight text-foreground sm:text-6xl md:text-7xl"
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
            className="mx-auto mt-6 max-w-2xl text-balance text-base text-muted-foreground sm:text-lg"
          >
            {t("hero.subtitle")}
          </motion.p>

          {/* Search */}
          <motion.div variants={fadeUp} custom={3} className="mx-auto mt-10 max-w-2xl">
            <div ref={containerRef} className="group relative">
              <div className="absolute -inset-px rounded-2xl bg-gradient-to-r from-primary/30 via-primary-glow/40 to-accent/30 opacity-60 blur-md transition group-focus-within:opacity-100" />
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  runSearch(query.trim());
                }}
                className="relative flex items-center gap-2 rounded-2xl border border-border bg-card/90 p-2 shadow-elevated backdrop-blur-xl"
              >
                <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
                  <Search className="size-4" />
                </div>
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onFocus={() => suggestions.length > 0 && setOpen(true)}
                  placeholder={t("hero.search_placeholder")}
                  className="min-w-0 flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground/80 focus:outline-none sm:text-[15px]"
                />
                <span className="hidden items-center gap-1 rounded-full bg-primary/8 px-2.5 py-1 text-[11px] font-semibold text-primary sm:inline-flex">
                  <Sparkles className="size-3" />
                  {t("hero.ai_hint")}
                </span>
                <button
                  type="submit"
                  className="inline-flex items-center gap-1 rounded-xl bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition hover:shadow-glow"
                >
                  {t("hero.search_button")}
                </button>
              </form>

              {open && suggestions.length > 0 && (
                <div className="absolute inset-x-0 top-full z-20 mt-2 overflow-hidden rounded-2xl border border-border bg-card shadow-elevated">
                  {suggestions.map((s, i) => (
                    <button
                      key={`${s.text}-${i}`}
                      type="button"
                      onClick={() => runSearch(s.text)}
                      className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm text-foreground hover:bg-muted"
                    >
                      <Search className="size-3.5 text-muted-foreground" />
                      {s.text}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Suggestion chips */}
            <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
              {[
                { icon: Building2, label: "Apartments in Tashkent", q: "kvartira" },
                { icon: BedDouble, label: "Hotels in Dubai", q: "mehmonxona" },
                { icon: Hammer, label: "Builders near me", q: "qurilish" },
                { icon: MapPin, label: "Land in Bali", q: "yer" },
              ].map((s, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => runSearch(s.q)}
                  className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card/60 px-3 py-1.5 text-xs text-foreground/70 backdrop-blur transition hover:border-primary/40 hover:bg-card hover:text-foreground"
                >
                  <s.icon className="size-3" />
                  {s.label}
                </button>
              ))}
            </div>
          </motion.div>
        </motion.div>

        {/* Floating glass cards */}
        <div className="relative mx-auto mt-20 hidden max-w-5xl md:block">
          <FloatingCard
            className="absolute -left-6 top-0"
            delay={0.2}
            title="AI valuation"
            value="$284,500"
            sub="+2.4% this month"
            tone="primary"
          />
          <FloatingCard
            className="absolute -right-6 top-8"
            delay={0.4}
            title="New listing"
            value="3-bed · Tashkent"
            sub="Verified · 4 min ago"
            tone="accent"
          />
          <FloatingCard
            className="absolute left-1/2 top-32 -translate-x-1/2"
            delay={0.6}
            title="Booked tonight"
            value="Hotel · Istanbul"
            sub="Instant confirm"
            tone="success"
          />
        </div>
      </div>
    </section>
  );
}

function FloatingCard({
  className = "",
  delay = 0,
  title,
  value,
  sub,
  tone,
}: {
  className?: string;
  delay?: number;
  title: string;
  value: string;
  sub: string;
  tone: "primary" | "accent" | "success";
}) {
  const dot = tone === "primary" ? "bg-primary" : tone === "accent" ? "bg-accent" : "bg-success";
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
      className={`glass animate-float w-56 rounded-2xl p-4 shadow-elevated ${className}`}
      style={{ animationDelay: `${delay}s` }}
    >
      <div className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
        <span className={`size-1.5 rounded-full ${dot}`} />
        {title}
      </div>
      <div className="font-display mt-2 text-xl font-semibold text-foreground">{value}</div>
      <div className="mt-1 text-xs text-muted-foreground">{sub}</div>
    </motion.div>
  );
}
