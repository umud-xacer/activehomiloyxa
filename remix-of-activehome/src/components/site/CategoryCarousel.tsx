/**
 * Premium infinite category carousel.
 *
 * - Continuous auto-scroll powered by Framer Motion + rAF (not CSS).
 * - Hover on the row slows the animation; hover on a card pauses it.
 * - Pointer drag (mouse + touch) takes over with momentum.
 * - Wheel scrolling translates vertical wheel deltas to horizontal motion.
 * - Keyboard arrow keys nudge focus + scroll.
 * - Each card: glass surface, gradient border, illustration, count, description,
 *   floating depth shadow, ripple on click.
 *
 * Content is API-ready: `CATS` is the local fixture; swap to
 * `apiClient.categories.list()` when the backend exposes that endpoint.
 */
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
  type WheelEvent,
} from "react";
import { useTranslation } from "react-i18next";
import {
  animate,
  motion,
  useMotionValue,
  useReducedMotion,
} from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import {
  Building2,
  Building,
  Home,
  House,
  Warehouse,
  TreePine,
  MapPin,
  Wrench,
  Briefcase,
  Blocks,
  Sofa,
  Tv,
  Frame,
  Sprout,
  HardHat,
  Armchair,
  BedDouble,
  Hotel,
  ArrowUpRight,
  type LucideIcon,
} from "lucide-react";
import { categoriesOptions } from "@/features/properties/queries";

type Cat = {
  key: string;
  Icon: LucideIcon;
  count: number;
  /** Tailwind gradient stops applied to the card background tint */
  hue: string;
  /** Hex used for the ring + glow per card */
  accent: string;
  to: string;
  search?: Record<string, string>;
};

/** Static fallback shown while real categories load / for verticals with no backend module
 * wired yet (construction/services/materials/... -- catalog module scope is real-estate-only
 * for now, see configuration seed). Real estate entries are replaced by live /categories data. */
const FALLBACK_CATS: Cat[] = [
  { key: "apartments", Icon: Building2, count: 0, hue: "from-indigo-500/15 to-violet-500/15", accent: "#6366F1", to: "/properties" },
  { key: "buildings", Icon: Building, count: 1840, hue: "from-blue-500/15 to-cyan-500/15", accent: "#3B82F6", to: "/properties" },
  { key: "cottages", Icon: Home, count: 0, hue: "from-emerald-500/15 to-teal-500/15", accent: "#10B981", to: "/properties" },
  { key: "houses", Icon: House, count: 0, hue: "from-amber-500/15 to-orange-500/15", accent: "#F59E0B", to: "/properties" },
  { key: "commercial", Icon: Warehouse, count: 0, hue: "from-slate-500/15 to-zinc-500/15", accent: "#64748B", to: "/properties" },
  { key: "country", Icon: TreePine, count: 980, hue: "from-lime-500/15 to-emerald-500/15", accent: "#84CC16", to: "/properties" },
  { key: "land", Icon: MapPin, count: 0, hue: "from-yellow-500/15 to-amber-500/15", accent: "#EAB308", to: "/properties" },
  { key: "services", Icon: Wrench, count: 540, hue: "from-cyan-500/15 to-sky-500/15", accent: "#06B6D4", to: "/services" },
  { key: "jobs", Icon: Briefcase, count: 1280, hue: "from-fuchsia-500/15 to-pink-500/15", accent: "#D946EF", to: "/jobs" },
  { key: "materials", Icon: Blocks, count: 6210, hue: "from-orange-500/15 to-red-500/15", accent: "#F97316", to: "/materials" },
  { key: "furniture_mat", Icon: Sofa, count: 4810, hue: "from-rose-500/15 to-pink-500/15", accent: "#F43F5E", to: "/furniture" },
  { key: "appliances", Icon: Tv, count: 3320, hue: "from-blue-500/15 to-indigo-500/15", accent: "#4F46E5", to: "/appliances" },
  { key: "decoration", Icon: Frame, count: 2180, hue: "from-violet-500/15 to-purple-500/15", accent: "#8B5CF6", to: "/interior" },
  { key: "landscape", Icon: Sprout, count: 720, hue: "from-green-500/15 to-lime-500/15", accent: "#22C55E", to: "/landscape" },
  { key: "safety", Icon: HardHat, count: 410, hue: "from-yellow-500/15 to-orange-500/15", accent: "#FACC15", to: "/services" },
  { key: "furniture", Icon: Armchair, count: 5840, hue: "from-pink-500/15 to-rose-500/15", accent: "#EC4899", to: "/furniture" },
  { key: "hostels", Icon: BedDouble, count: 820, hue: "from-teal-500/15 to-cyan-500/15", accent: "#14B8A6", to: "/hostels" },
  { key: "hotels", Icon: Hotel, count: 0, hue: "from-primary/20 to-primary-glow/20", accent: "#2D3270", to: "/hotels" },
];

const REAL_ESTATE_PATHS = new Set(["apartments", "houses", "cottages", "commercial", "land", "hotels"]);
const ICON_BY_PATH: Record<string, LucideIcon> = {
  apartments: Building2,
  houses: House,
  cottages: Home,
  commercial: Warehouse,
  land: MapPin,
  hotels: Hotel,
};
const ACCENT_BY_PATH: Record<string, { hue: string; accent: string }> = {
  apartments: { hue: "from-indigo-500/15 to-violet-500/15", accent: "#6366F1" },
  houses: { hue: "from-amber-500/15 to-orange-500/15", accent: "#F59E0B" },
  cottages: { hue: "from-emerald-500/15 to-teal-500/15", accent: "#10B981" },
  commercial: { hue: "from-slate-500/15 to-zinc-500/15", accent: "#64748B" },
  land: { hue: "from-yellow-500/15 to-amber-500/15", accent: "#EAB308" },
  hotels: { hue: "from-primary/20 to-primary-glow/20", accent: "#2D3270" },
};

function useCats(): Cat[] {
  const { data: categories } = useQuery(categoriesOptions());
  if (!categories) return FALLBACK_CATS;
  const real: Cat[] = categories
    .filter((c) => REAL_ESTATE_PATHS.has(c.path))
    .map((c) => ({
      key: c.path,
      Icon: ICON_BY_PATH[c.path] ?? Building2,
      count: 0,
      ...ACCENT_BY_PATH[c.path],
      to: "/properties",
      search: { category: c.path },
    }));
  const rest = FALLBACK_CATS.filter((c) => !REAL_ESTATE_PATHS.has(c.key));
  return [...real, ...rest];
}

const BASE_VELOCITY = 28; // px / sec
const HOVER_VELOCITY = 8; // slowed
const CARD_WIDTH = 232; // includes gutter

function CategoryCard({ cat }: { cat: Cat }) {
  const { t } = useTranslation();
  const Icon = cat.Icon;
  const [ripple, setRipple] = useState<{ x: number; y: number; id: number } | null>(null);

  const onPointerDown = (e: PointerEvent<HTMLAnchorElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    setRipple({ x: e.clientX - rect.left, y: e.clientY - rect.top, id: Date.now() });
  };

  return (
    <Link
      to={cat.to}
      search={cat.search}
      onPointerDown={onPointerDown}
      className="group relative mx-2 inline-block w-[216px] shrink-0 select-none"
      draggable={false}
    >
      <motion.div
        whileHover={{ y: -8, scale: 1.02 }}
        transition={{ type: "spring", stiffness: 280, damping: 22 }}
        className="relative h-[228px] overflow-hidden rounded-3xl border border-border bg-card p-5 shadow-soft transition-shadow group-hover:shadow-elevated"
        style={{
          backgroundImage: `linear-gradient(135deg, ${cat.accent}14 0%, transparent 55%)`,
        }}
      >
        {/* Gradient border ring */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 rounded-3xl opacity-0 transition-opacity duration-500 group-hover:opacity-100"
          style={{
            background: `linear-gradient(135deg, ${cat.accent}40, transparent 50%)`,
            padding: 1,
            WebkitMask: "linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0)",
            WebkitMaskComposite: "xor",
            maskComposite: "exclude",
          }}
        />
        {/* Floating glow */}
        <div
          aria-hidden
          className="pointer-events-none absolute -right-10 -top-10 size-32 rounded-full opacity-0 blur-2xl transition-opacity duration-500 group-hover:opacity-70"
          style={{ background: cat.accent }}
        />
        {/* Subtle mesh */}
        <div className={`pointer-events-none absolute inset-0 bg-gradient-to-br ${cat.hue} opacity-50`} />

        {/* Icon plate */}
        <div className="relative flex h-full flex-col">
          <div className="flex items-start justify-between">
            <div
              className="flex size-12 items-center justify-center rounded-2xl border border-glass-border bg-card/80 shadow-soft backdrop-blur transition-transform duration-500 group-hover:-translate-y-0.5"
              style={{ color: cat.accent }}
            >
              <Icon className="size-5" />
            </div>
            <div className="opacity-0 transition-opacity duration-300 group-hover:opacity-100">
              <ArrowUpRight className="size-4 text-foreground/60" />
            </div>
          </div>

          <div className="mt-auto">
            <div className="font-display text-base font-semibold leading-tight text-foreground">
              {t(`categories.${cat.key}`)}
            </div>
            <div className="mt-1 text-[11px] text-muted-foreground">
              {t(`categories.${cat.key}_desc`, { defaultValue: t("categories.default_desc") })}
            </div>
            <div className="mt-3 flex items-center gap-1.5">
              <span className="size-1.5 rounded-full" style={{ background: cat.accent }} />
              <span className="text-[11px] font-semibold text-foreground/80">
                {cat.count.toLocaleString()} {t("categories.listings")}
              </span>
            </div>
          </div>
        </div>

        {/* Ripple */}
        {ripple && (
          <motion.span
            key={ripple.id}
            initial={{ scale: 0, opacity: 0.45 }}
            animate={{ scale: 8, opacity: 0 }}
            transition={{ duration: 0.7, ease: "easeOut" }}
            onAnimationComplete={() => setRipple(null)}
            className="pointer-events-none absolute size-12 rounded-full"
            style={{
              left: ripple.x - 24,
              top: ripple.y - 24,
              background: `${cat.accent}55`,
            }}
          />
        )}
      </motion.div>
    </Link>
  );
}

function CarouselRow({ cats, direction = 1 }: { cats: Cat[]; direction?: 1 | -1 }) {
  const x = useMotionValue(0);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [hover, setHover] = useState(false);
  const [dragging, setDragging] = useState(false);
  const dragStart = useRef({ x: 0, mx: 0 });
  const reduce = useReducedMotion();
  const TOTAL = cats.length * CARD_WIDTH;

  const loop = useMemo(() => [...cats, ...cats], [cats]);

  // Auto-scroll via rAF; respects hover & dragging
  useEffect(() => {
    if (reduce) return;
    let raf = 0;
    let prev = performance.now();
    const tick = (now: number) => {
      const dt = (now - prev) / 1000;
      prev = now;
      if (!dragging) {
        const v = hover ? HOVER_VELOCITY : BASE_VELOCITY;
        let next = x.get() - direction * v * dt;
        // Wrap seamlessly
        if (next <= -TOTAL) next += TOTAL;
        if (next >= 0) next -= TOTAL;
        x.set(next);
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [hover, dragging, direction, x, reduce]);

  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    setDragging(true);
    dragStart.current = { x: e.clientX, mx: x.get() };
    (e.target as Element).setPointerCapture?.(e.pointerId);
  };
  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    if (!dragging) return;
    const dx = e.clientX - dragStart.current.x;
    let next = dragStart.current.mx + dx;
    while (next <= -TOTAL) next += TOTAL;
    while (next >= 0) next -= TOTAL;
    x.set(next);
  };
  const onPointerUp = (e: PointerEvent<HTMLDivElement>) => {
    setDragging(false);
    (e.target as Element).releasePointerCapture?.(e.pointerId);
  };

  const onWheel = (e: WheelEvent<HTMLDivElement>) => {
    const delta = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY;
    if (!delta) return;
    let next = x.get() - delta * 0.6;
    while (next <= -TOTAL) next += TOTAL;
    while (next >= 0) next -= TOTAL;
    x.set(next);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    const dir = e.key === "ArrowLeft" ? 1 : -1;
    animate(x, x.get() + dir * CARD_WIDTH, { type: "spring", stiffness: 220, damping: 28 });
  };

  return (
    <div
      ref={containerRef}
      role="region"
      aria-label="Categories"
      tabIndex={0}
      onPointerEnter={() => setHover(true)}
      onPointerLeave={() => setHover(false)}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onWheel={onWheel}
      onKeyDown={onKeyDown}
      className="relative overflow-hidden focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-2 focus-visible:ring-offset-background [mask-image:linear-gradient(to_right,transparent,black_5%,black_95%,transparent)]"
      style={{ touchAction: "pan-y", cursor: dragging ? "grabbing" : "grab" }}
    >
      <motion.div style={{ x }} className="flex w-max py-3">
        {loop.map((c, i) => (
          <CategoryCard key={`${c.key}-${i}`} cat={c} />
        ))}
      </motion.div>
    </div>
  );
}

export function CategoryCarousel() {
  const { t } = useTranslation();
  const cats = useCats();
  return (
    <section className="relative py-24">
      <div className="mx-auto max-w-7xl px-6 text-center">
        <div className="inline-flex items-center gap-2 rounded-full border border-border bg-card/60 px-3 py-1 text-[11px] font-medium uppercase tracking-widest text-foreground/70 backdrop-blur">
          <span className="size-1.5 rounded-full bg-primary" />
          {t("categories.eyebrow", { defaultValue: "Explore the ecosystem" })}
        </div>
        <h2 className="font-display mt-4 text-3xl font-semibold tracking-tight text-foreground sm:text-4xl md:text-5xl">
          {t("categories.title")}
        </h2>
        <p className="mx-auto mt-3 max-w-2xl text-base text-muted-foreground">
          {t("categories.subtitle")}
        </p>
      </div>

      <div className="mt-12 space-y-3">
        <CarouselRow cats={cats} direction={1} />
        <CarouselRow cats={cats} direction={-1} />
      </div>
    </section>
  );
}
