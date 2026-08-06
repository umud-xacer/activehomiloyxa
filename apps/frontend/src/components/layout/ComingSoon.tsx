import { Sparkles } from "lucide-react";
import { motion } from "framer-motion";
import { PropertyGridSkeleton } from "@/components/data/PropertyCardSkeleton";

interface Props {
  wave: 1 | 2 | 3 | 4 | 5;
  page: string;
}

export function ComingSoon({ wave, page }: Props) {
  return (
    <section className="mx-auto max-w-7xl px-6 py-16">
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        className="relative mb-10 overflow-hidden rounded-3xl border border-border bg-card p-8 shadow-soft"
      >
        <div className="gradient-mesh absolute inset-0 -z-10 opacity-60" />
        <div className="inline-flex items-center gap-2 rounded-full border border-border bg-card/60 px-3 py-1 text-xs font-medium text-foreground/70 backdrop-blur">
          <Sparkles className="size-3 text-primary" />
          Shipping in Wave {wave}
        </div>
        <h2 className="font-display mt-4 text-2xl font-semibold text-foreground sm:text-3xl">
          {page} is being polished
        </h2>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          The architecture, design tokens and data layer for this page are already in place. A
          premium, fully interactive surface lands in the next wave.
        </p>
      </motion.div>
      <PropertyGridSkeleton count={8} />
    </section>
  );
}
