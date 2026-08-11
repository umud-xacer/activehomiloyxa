/**
 * A category's visual tile -- real photo when the category (or, for icon/color, its nearest
 * themed ancestor) has one, otherwise a themed gradient + icon. Used for the subcategory grid on
 * `routes/categories/$.tsx` (replacing what used to be a bare row of text pills) and reusable
 * anywhere else a category needs to look like something rather than just say something.
 */
import type { LucideIcon } from "lucide-react";

export function CategoryTile({
  imageUrl,
  icon: Icon,
  accentColor,
  size = "md",
  className = "",
}: {
  imageUrl?: string | null;
  icon: LucideIcon;
  accentColor: string;
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  const dims = size === "lg" ? "size-16" : size === "sm" ? "size-9" : "size-12";
  const iconDims = size === "lg" ? "size-7" : size === "sm" ? "size-4" : "size-5";

  if (imageUrl) {
    return (
      <div
        className={`${dims} shrink-0 overflow-hidden rounded-2xl bg-cover bg-center ${className}`}
        style={{ backgroundImage: `url(${imageUrl})` }}
        aria-hidden
      />
    );
  }

  return (
    <div
      className={`${dims} flex shrink-0 items-center justify-center rounded-2xl ${className}`}
      style={{
        background: `linear-gradient(135deg, ${accentColor}26, ${accentColor}0d)`,
        color: accentColor,
      }}
      aria-hidden
    >
      <Icon className={iconDims} />
    </div>
  );
}
