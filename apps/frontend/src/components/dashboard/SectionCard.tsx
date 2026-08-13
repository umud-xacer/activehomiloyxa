import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { motion } from "framer-motion";

interface SectionCardProps {
  title: string;
  icon?: LucideIcon;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  /** Stagger delay for the entrance animation when several cards mount together. */
  index?: number;
  /** Remove default padding on the content area (e.g. for a full-bleed table). */
  noPadding?: boolean;
}

export function SectionCard({
  title,
  icon: Icon,
  description,
  action,
  children,
  className = "",
  index = 0,
  noPadding = false,
}: SectionCardProps) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05, duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
      className={`overflow-hidden rounded-2xl border border-border bg-card shadow-soft ${className}`}
    >
      <div className="flex flex-col gap-3 border-b border-border/70 px-6 py-4 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
        <div className="flex items-center gap-2.5">
          {Icon && (
            <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Icon className="size-4" />
            </div>
          )}
          <div>
            <h2 className="font-display text-base font-semibold leading-tight text-foreground">
              {title}
            </h2>
            {description && <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>}
          </div>
        </div>
        {action && <div className="sm:shrink-0">{action}</div>}
      </div>
      <div className={noPadding ? "" : "p-6"}>{children}</div>
    </motion.section>
  );
}
