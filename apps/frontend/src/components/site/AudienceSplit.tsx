import { Link } from "@tanstack/react-router";
import { motion } from "framer-motion";
import { ArrowRight, Building2, Home } from "lucide-react";

/** The homepage's own "no confusion" entry point (Monetization/B2C-B2B task): two unambiguous
 * paths right below the search hero, before any other section competes for attention --
 * "Ko'chmas mulk va E'lonlar" (individuals: browse/list property) vs. "Tashkilotlar"
 * (legal entities: the B2B organizations directory, `/companies`). */
export function AudienceSplit() {
  return (
    <section className="relative mx-auto max-w-6xl px-4 py-10 sm:px-6">
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
        >
          <Link
            to="/properties"
            className="group flex h-full items-center gap-5 overflow-hidden rounded-3xl border border-border bg-card p-7 shadow-soft transition hover:border-primary/40 hover:shadow-elevated"
          >
            <div className="flex size-14 shrink-0 items-center justify-center rounded-2xl bg-primary/10 text-primary">
              <Home className="size-6" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="font-display text-xl font-semibold text-foreground">
                Ko'chmas mulk va E'lonlar
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                Uy, kvartira, yer va binolarni qidiring, ijaraga bering yoki soting.
              </p>
            </div>
            <ArrowRight className="size-5 shrink-0 text-muted-foreground transition group-hover:translate-x-1 group-hover:text-primary" />
          </Link>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.5, delay: 0.08, ease: [0.22, 1, 0.36, 1] }}
        >
          <Link
            to="/organizations"
            className="group flex h-full items-center gap-5 overflow-hidden rounded-3xl border border-border bg-card p-7 shadow-soft transition hover:border-primary/40 hover:shadow-elevated"
          >
            <div className="flex size-14 shrink-0 items-center justify-center rounded-2xl bg-primary/10 text-primary">
              <Building2 className="size-6" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="font-display text-xl font-semibold text-foreground">Tashkilotlar</p>
              <p className="mt-1 text-sm text-muted-foreground">
                Qurilish, ta'mirlash va dizayn bo'yicha tasdiqlangan tashkilotlar katalogi.
              </p>
            </div>
            <ArrowRight className="size-5 shrink-0 text-muted-foreground transition group-hover:translate-x-1 group-hover:text-primary" />
          </Link>
        </motion.div>
      </div>
    </section>
  );
}
