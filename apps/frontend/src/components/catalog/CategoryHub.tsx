/**
 * The "Hub" strip beneath a category page's Hero -- a row of premium pill-cards for curated
 * collections (new/cheapest/priciest/recommended/discounted). Every option here is backed by a
 * real backend sort or a real client-side filter over already-fetched data (e.g. `featured`,
 * itself derived from a listing's real `promotion` field) -- deliberately no fabricated "AI"
 * collection with no real signal behind it. Shared between `PropertyDirectionView` and
 * `CatalogDirectionView` (`routes/categories/$slug.tsx`) so both directions get the same premium
 * Hub treatment instead of a plain `<select>`.
 */
import type { LucideIcon } from "lucide-react";
import { motion } from "framer-motion";

export interface HubOption<T extends string> {
  value: T;
  label: string;
  icon: LucideIcon;
}

export function CategoryHub<T extends string>({
  options,
  value,
  onChange,
}: {
  options: HubOption<T>[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2.5">
      {options.map((opt, i) => {
        const Icon = opt.icon;
        const active = opt.value === value;
        return (
          <motion.button
            key={opt.value}
            type="button"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.04, duration: 0.35 }}
            onClick={() => onChange(opt.value)}
            className={`inline-flex items-center gap-2 rounded-2xl border px-4 py-2.5 text-sm font-medium shadow-soft transition ${
              active
                ? "border-primary bg-primary text-primary-foreground shadow-elevated"
                : "border-border bg-card text-foreground/80 hover:border-primary/40 hover:text-foreground"
            }`}
          >
            <Icon className="size-4" />
            {opt.label}
          </motion.button>
        );
      })}
    </div>
  );
}
