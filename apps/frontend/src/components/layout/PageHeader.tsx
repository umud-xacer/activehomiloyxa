import { Link } from "@tanstack/react-router";
import { ChevronRight, type LucideIcon } from "lucide-react";
import { motion } from "framer-motion";
import type { ReactNode } from "react";
import { Container } from "./Container";

export interface Crumb {
  label: string;
  to?: string;
}

interface Props {
  eyebrow?: string;
  title: string;
  /** A short, punchy per-category line (`Category.heroTagline`) rendered right under the title,
   * distinct from `description` (which callers often use for a computed stat like a listing
   * count) -- this is what gives each category's Hero its own voice ("Har bir qurilish uchun
   * ishonchli materiallar" vs "Hashamat va qulaylik bir joyda"). */
  tagline?: string | null;
  description?: string;
  crumbs?: Crumb[];
  actions?: ReactNode;
  /** Admin-authored per-category Hero background (`Category.heroImageUrl`) -- when set, replaces
   * the generic gradient-mesh with a full-bleed cover image + dark overlay so text stays legible,
   * giving each category its own "vizual muhit" without a bespoke per-category component. */
  backgroundImageUrl?: string | null;
  /** Admin-authored per-category accent (`Category.accentColor`, any CSS color value) -- tints
   * the eyebrow pill so a category's Hero reads as its own environment while staying inside the
   * shared PageHeader template. Also tints the no-photo fallback background (below) so a
   * subcategory with no Hero photo of its own still reads as part of its category family instead
   * of falling back to one flat generic gray gradient for every category on the site. */
  accentColor?: string | null;
  /** Large translucent watermark icon shown on the no-photo fallback background, tinted by
   * `accentColor`. Purely decorative -- omit for a plain tinted gradient. */
  icon?: LucideIcon;
}

export function PageHeader({
  eyebrow,
  title,
  tagline,
  description,
  crumbs,
  actions,
  backgroundImageUrl,
  accentColor,
  icon: Icon,
}: Props) {
  const themed = Boolean(backgroundImageUrl);
  return (
    <section
      className={`relative isolate overflow-hidden border-b border-border pt-32 pb-12 ${themed ? "text-white" : ""}`}
    >
      {backgroundImageUrl ? (
        <>
          <div
            className="absolute inset-0 -z-20 bg-cover bg-center"
            style={{ backgroundImage: `url(${backgroundImageUrl})` }}
            aria-hidden
          />
          <div className="absolute inset-0 -z-10 bg-gradient-to-t from-black/80 via-black/50 to-black/20" />
        </>
      ) : accentColor ? (
        <>
          <div
            className="absolute inset-0 -z-10"
            style={{
              background: `linear-gradient(135deg, ${accentColor}1f 0%, transparent 55%)`,
            }}
            aria-hidden
          />
          <div className="gradient-mesh absolute inset-0 -z-10 opacity-40" />
          {Icon && (
            <Icon
              className="pointer-events-none absolute -right-6 -top-6 -z-10 size-56 opacity-[0.06] sm:size-72"
              style={{ color: accentColor }}
              aria-hidden
            />
          )}
        </>
      ) : (
        <div className="gradient-mesh absolute inset-0 -z-10 opacity-60" />
      )}
      {!themed && <div className="absolute inset-0 -z-20 bg-card/40" aria-hidden />}
      <Container>
        {crumbs && crumbs.length > 0 && (
          <nav
            className={`mb-4 flex items-center gap-1 text-xs ${themed ? "text-white/70" : "text-muted-foreground"}`}
          >
            {crumbs.map((c, i) => (
              <span key={i} className="inline-flex items-center gap-1">
                {c.to ? (
                  <Link to={c.to} className={themed ? "hover:text-white" : "hover:text-foreground"}>
                    {c.label}
                  </Link>
                ) : (
                  <span className={themed ? "text-white" : "text-foreground"}>{c.label}</span>
                )}
                {i < crumbs.length - 1 && <ChevronRight className="size-3" />}
              </span>
            ))}
          </nav>
        )}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
          className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between"
        >
          <div className="max-w-3xl">
            {eyebrow && (
              <div
                className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium backdrop-blur ${
                  themed
                    ? "border-white/30 bg-white/10 text-white"
                    : "border-border bg-card/60 text-foreground/70"
                }`}
                style={accentColor ? { borderColor: accentColor, color: accentColor } : undefined}
              >
                {eyebrow}
              </div>
            )}
            <h1
              className={`font-display text-hero mt-4 font-semibold ${themed ? "text-white" : "text-foreground"}`}
            >
              {title}
            </h1>
            {tagline && (
              <p
                className={`mt-2 max-w-2xl text-lg font-medium ${themed ? "text-white/90" : "text-foreground/80"}`}
                style={accentColor && !themed ? { color: accentColor } : undefined}
              >
                {tagline}
              </p>
            )}
            {description && (
              <p
                className={`mt-3 max-w-2xl text-base ${themed ? "text-white/80" : "text-muted-foreground"}`}
              >
                {description}
              </p>
            )}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </motion.div>
      </Container>
    </section>
  );
}
