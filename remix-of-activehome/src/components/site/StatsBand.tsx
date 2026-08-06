import { useTranslation } from "react-i18next";
import { motion, useInView, useMotionValue, useTransform, animate } from "framer-motion";
import { useEffect, useRef } from "react";

function Counter({ to, suffix = "" }: { to: number; suffix?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, margin: "-80px" });
  const mv = useMotionValue(0);
  const rounded = useTransform(mv, (v) => Math.floor(v).toLocaleString());

  useEffect(() => {
    if (inView) {
      const controls = animate(mv, to, { duration: 1.6, ease: [0.22, 1, 0.36, 1] });
      return () => controls.stop();
    }
  }, [inView, to, mv]);

  return (
    <span ref={ref} className="tabular-nums">
      <motion.span>{rounded}</motion.span>
      {suffix}
    </span>
  );
}

export function StatsBand() {
  const { t } = useTranslation();
  const stats = [
    { value: 1240000, suffix: "+", key: "listings" },
    { value: 380, suffix: "+", key: "cities" },
    { value: 12500, suffix: "+", key: "partners" },
    { value: 98, suffix: "%", key: "satisfaction" },
  ];

  return (
    <section className="relative isolate overflow-hidden border-y border-border bg-surface/60">
      <div
        className="absolute inset-0 -z-10 bg-cover bg-center opacity-15"
        style={{ backgroundImage: `url(/background.jpg)` }}
        aria-hidden
      />
      <div className="mx-auto grid max-w-7xl grid-cols-2 gap-y-8 px-6 py-12 sm:grid-cols-4">
        {stats.map((s) => (
          <div key={s.key} className="text-center">
            <div className="font-display text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
              <Counter to={s.value} suffix={s.suffix} />
            </div>
            <div className="mt-1 text-xs uppercase tracking-wider text-muted-foreground">
              {t(`stats.${s.key}`)}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
