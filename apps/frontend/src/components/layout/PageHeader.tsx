import { Link } from "@tanstack/react-router";
import { ChevronRight } from "lucide-react";
import { motion } from "framer-motion";
import type { ReactNode } from "react";

export interface Crumb {
  label: string;
  to?: string;
}

interface Props {
  eyebrow?: string;
  title: string;
  description?: string;
  crumbs?: Crumb[];
  actions?: ReactNode;
}

export function PageHeader({ eyebrow, title, description, crumbs, actions }: Props) {
  return (
    <section className="relative isolate overflow-hidden border-b border-border bg-card/40 pt-32 pb-12">
      <div className="gradient-mesh absolute inset-0 -z-10 opacity-60" />
      <div className="mx-auto max-w-7xl px-6">
        {crumbs && crumbs.length > 0 && (
          <nav className="mb-4 flex items-center gap-1 text-xs text-muted-foreground">
            {crumbs.map((c, i) => (
              <span key={i} className="inline-flex items-center gap-1">
                {c.to ? (
                  <Link to={c.to} className="hover:text-foreground">
                    {c.label}
                  </Link>
                ) : (
                  <span className="text-foreground">{c.label}</span>
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
              <div className="inline-flex items-center rounded-full border border-border bg-card/60 px-3 py-1 text-xs font-medium text-foreground/70 backdrop-blur">
                {eyebrow}
              </div>
            )}
            <h1 className="font-display mt-4 text-4xl font-semibold tracking-tight text-foreground sm:text-5xl">
              {title}
            </h1>
            {description && (
              <p className="mt-3 max-w-2xl text-base text-muted-foreground">{description}</p>
            )}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </motion.div>
      </div>
    </section>
  );
}
