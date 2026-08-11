/**
 * The homepage "proof strip" -- moved out of `Hero.tsx` (Task: homepage reorder) so it can render
 * as its own dark-blue section after `MissionBand` instead of living inside Hero's own background.
 * Numbers come from `getPlatformStats` (real live search total + admin-editable settings), never
 * hardcoded.
 */
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { motion, useInView, useMotionValue, useTransform, animate } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { getPlatformStats } from "@/lib/platform-stats-client";

function Counter({ to, suffix = "" }: { to: number; suffix?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, margin: "-40px" });
  const mv = useMotionValue(0);
  const rounded = useTransform(mv, (v) => Math.floor(v).toLocaleString());

  useEffect(() => {
    if (inView) {
      const controls = animate(mv, to, { duration: 1.4, ease: [0.22, 1, 0.36, 1] });
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

export function PlatformStatsBand() {
  const { t } = useTranslation();
  const { data } = useQuery({
    queryKey: ["platform-stats"],
    queryFn: getPlatformStats,
    staleTime: 5 * 60_000,
  });

  const stats = [
    { value: data?.activeListings ?? 0, suffix: "+", key: "listings" },
    { value: data?.cities ?? 0, suffix: "+", key: "cities" },
    { value: data?.partners ?? 0, suffix: "+", key: "partners" },
    { value: data?.satisfactionPercent ?? 0, suffix: "%", key: "satisfaction" },
  ];

  if (!data) return null;

  return (
    <section className="hero-dark relative isolate overflow-hidden bg-background py-12 text-foreground">
      <div className="gradient-mesh absolute inset-0 -z-10" />
      <div className="mx-auto max-w-4xl px-6">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-60px" }}
          transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
          className="flex flex-wrap items-center justify-center gap-x-12 gap-y-6"
        >
          {stats.map((s) => (
            <div key={s.key} className="flex flex-col items-center gap-1 text-center">
              <span className="font-display text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
                <Counter to={s.value} suffix={s.suffix} />
              </span>
              <span className="text-[11px] uppercase tracking-wider text-muted-foreground">
                {t(`stats.${s.key}`)}
              </span>
            </div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}
