import type { ReactNode } from "react";
import { motion } from "framer-motion";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader, type Crumb } from "@/components/layout/PageHeader";

/**
 * Shared shell for the footer's legal/info pages (Terms, FAQ, Ad rules, Refund policy, Public
 * offer, Privacy, Security policy -- `ActiveHome_Footer_Prezentatsiya.html`'s 8 sections).
 * Same visual language as `about.tsx` (rounded-2xl cards, `font-display` headings) so these read
 * as part of the same site rather than a bolted-on legal-boilerplate template.
 */
export function LegalPage({
  eyebrow,
  title,
  description,
  updated,
  crumbs,
  children,
}: {
  eyebrow: string;
  title: string;
  description?: string;
  /** e.g. "Oxirgi yangilanish: 15-fevral, 2026" -- shown under the header when the document is
   * versioned (privacy policy, public offer). Omit for pages that aren't dated. */
  updated?: string;
  crumbs?: Crumb[];
  children: ReactNode;
}) {
  return (
    <AppShell>
      <PageHeader
        eyebrow={eyebrow}
        title={title}
        description={description}
        crumbs={crumbs ?? [{ label: "Bosh sahifa", to: "/" }, { label: title }]}
      />
      <div className="mx-auto max-w-3xl px-4 pb-24 pt-10 lg:px-8">
        {updated && (
          <p className="mb-8 text-xs font-medium uppercase tracking-wider text-muted-foreground">
            {updated}
          </p>
        )}
        <div className="space-y-12">{children}</div>
      </div>
    </AppShell>
  );
}

export function LegalSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 12 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.5 }}
    >
      <h2 className="font-display text-xl font-semibold text-foreground">{title}</h2>
      <div className="mt-3 space-y-3 text-sm leading-relaxed text-muted-foreground">{children}</div>
    </motion.section>
  );
}

export function LegalList({ items }: { items: ReactNode[] }) {
  return (
    <ul className="space-y-2.5">
      {items.map((item, i) => (
        <li key={i} className="flex items-start gap-2.5">
          <span className="mt-2 size-1.5 shrink-0 rounded-full bg-primary" />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

export function LegalBoxGrid({ items }: { items: { title: string; body: string }[] }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {items.map((item) => (
        <div
          key={item.title}
          className="rounded-2xl border border-border border-l-4 border-l-primary bg-card p-5 shadow-soft"
        >
          <h3 className="font-display text-sm font-semibold text-foreground">{item.title}</h3>
          <p className="mt-1.5 text-sm text-muted-foreground">{item.body}</p>
        </div>
      ))}
    </div>
  );
}

export function LegalBadges({ items, tone = "warn" }: { items: string[]; tone?: "warn" | "ok" }) {
  return (
    <div className="flex flex-wrap gap-2">
      {items.map((item) => (
        <span
          key={item}
          className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ${
            tone === "warn" ? "bg-destructive/10 text-destructive" : "bg-success/10 text-success"
          }`}
        >
          {item}
        </span>
      ))}
    </div>
  );
}
