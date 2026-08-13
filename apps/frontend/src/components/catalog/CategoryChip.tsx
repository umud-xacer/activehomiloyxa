/**
 * A single category/subcategory navigation pill -- round real-photo avatar (the category's own
 * `heroImageUrl`, already themed per category from the owner-admin panel / seeded hero-theme
 * table) + label, `rounded-full`. Replaces the old centered icon-over-label card grid: a real
 * photo per category reads far better at a glance than a generic Lucide icon, and a compact pill
 * row never pushes real listings below the fold the way a grid of large cards did. Shared between
 * `routes/categories/index.tsx` (top-level directory) and `routes/categories/$.tsx` (subcategory
 * nav within a category page) so both read as the same component, not two near-duplicates.
 */
import { Link } from "@tanstack/react-router";
import { motion } from "framer-motion";
import type { CategorySummary } from "@/lib/catalog-client";
import { categoryLabel } from "@/components/site/CategoryCarousel";
import { resolveCategoryIcon } from "@/lib/listing-kind";
import { CategoryTile } from "./CategoryTile";

export function CategoryChip({
  category,
  href,
  isActive = false,
  accentColor = "#6366f1",
  index = 0,
}: {
  category: CategorySummary;
  href: string;
  isActive?: boolean;
  accentColor?: string;
  index?: number;
}) {
  const icon = resolveCategoryIcon(category);
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: Math.min(index, 14) * 0.03, duration: 0.3 }}
    >
      <Link
        to={href}
        className={`group inline-flex items-center gap-2 rounded-full border py-2 pl-2 pr-4 shadow-soft transition ${
          isActive
            ? "border-primary bg-primary text-primary-foreground shadow-elevated"
            : "border-border bg-card text-foreground/85 hover:border-primary/40 hover:shadow-elevated"
        }`}
      >
        <span className="flex size-10 shrink-0 items-center justify-center overflow-hidden rounded-full bg-muted">
          {category.heroImageUrl ? (
            <img
              src={category.heroImageUrl}
              alt=""
              loading="lazy"
              className="size-full object-cover transition-transform duration-300 group-hover:scale-110"
            />
          ) : (
            <CategoryTile
              imageUrl={category.iconUrl}
              icon={icon}
              accentColor={isActive ? "currentColor" : accentColor}
              size="sm"
            />
          )}
        </span>
        <span className="whitespace-nowrap text-sm font-medium">
          {categoryLabel(category.name, "uz")}
        </span>
      </Link>
    </motion.div>
  );
}
