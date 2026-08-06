import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import { Link } from "@tanstack/react-router";
import {
  Home,
  Key,
  Hotel,
  Hammer,
  ShoppingBag,
  Palette,
  ShieldCheck,
  Wallet,
  MessageCircle,
  Truck,
  Wrench,
  TrendingUp,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

/** The 12 workflows the ecosystem's own subtitle promises -- previously 12 separate apps,
 * now 12 cards in one place. */
const ITEMS: { key: string; Icon: LucideIcon; to: string }[] = [
  { key: "buy", Icon: Home, to: "/properties" },
  { key: "rent", Icon: Key, to: "/properties" },
  { key: "stays", Icon: Hotel, to: "/hotels" },
  { key: "build", Icon: Hammer, to: "/construction" },
  { key: "shop", Icon: ShoppingBag, to: "/materials" },
  { key: "design", Icon: Palette, to: "/interior" },
  { key: "verify", Icon: ShieldCheck, to: "/verification" },
  { key: "finance", Icon: Wallet, to: "/payments" },
  { key: "connect", Icon: MessageCircle, to: "/messages" },
  { key: "move", Icon: Truck, to: "/services" },
  { key: "maintain", Icon: Wrench, to: "/maintenance" },
  { key: "invest", Icon: TrendingUp, to: "/invest" },
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

        <div className="mt-14 grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {ITEMS.map((it, i) => (
            <motion.div
              key={it.key}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-80px" }}
              transition={{ duration: 0.5, delay: i * 0.04, ease: [0.22, 1, 0.36, 1] }}
            >
              <Link
                to={it.to}
                className="group relative block h-full overflow-hidden rounded-3xl border border-border bg-card p-6 shadow-soft transition-all hover:-translate-y-1 hover:shadow-elevated"
              >
                <div className="absolute -right-10 -top-10 size-40 rounded-full bg-primary/8 blur-3xl opacity-0 transition-opacity group-hover:opacity-100" />
                <div className="relative">
                  <div className="flex size-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                    <it.Icon className="size-5" />
                  </div>
                  <h3 className="font-display mt-5 text-lg font-semibold text-foreground">
                    {t(`ecosystem.${it.key}_title`)}
                  </h3>
                  <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                    {t(`ecosystem.${it.key}_desc`)}
                  </p>
                </div>
              </Link>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
