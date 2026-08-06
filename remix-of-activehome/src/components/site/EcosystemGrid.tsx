import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import { Home, Key, Hotel, Hammer, ShoppingBag, Palette } from "lucide-react";
import type { LucideIcon } from "lucide-react";

const ITEMS: { key: string; Icon: LucideIcon }[] = [
  { key: "buy", Icon: Home },
  { key: "rent", Icon: Key },
  { key: "stays", Icon: Hotel },
  { key: "build", Icon: Hammer },
  { key: "shop", Icon: ShoppingBag },
  { key: "design", Icon: Palette },
];

export function EcosystemGrid() {
  const { t } = useTranslation();
  return (
    <section className="relative py-24">
      <div className="gradient-mesh pointer-events-none absolute inset-0 -z-10 opacity-50" />
      <div className="mx-auto max-w-7xl px-6">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="font-display text-3xl font-semibold tracking-tight text-foreground sm:text-4xl md:text-5xl">
            {t("ecosystem.title")}
          </h2>
          <p className="mt-3 text-base text-muted-foreground">{t("ecosystem.subtitle")}</p>
        </div>

        <div className="mt-14 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {ITEMS.map((it, i) => (
            <motion.div
              key={it.key}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-80px" }}
              transition={{ duration: 0.6, delay: i * 0.06, ease: [0.22, 1, 0.36, 1] }}
              className="group relative overflow-hidden rounded-3xl border border-border bg-card p-6 shadow-soft transition-all hover:-translate-y-1 hover:shadow-elevated"
            >
              <div className="absolute -right-10 -top-10 size-40 rounded-full bg-primary/8 blur-3xl opacity-0 transition-opacity group-hover:opacity-100" />
              <div className="relative">
                <div className="flex size-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                  <it.Icon className="size-5" />
                </div>
                <h3 className="font-display mt-5 text-xl font-semibold text-foreground">
                  {t(`ecosystem.${it.key}_title`)}
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                  {t(`ecosystem.${it.key}_desc`)}
                </p>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
