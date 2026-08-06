/**
 * Partners -- a premium "trusted by" panel: a soft glass card (matching Hero's search card and
 * CtaBand's banner card language) rather than a bare row sitting directly on the page background.
 * Muted by default, brand color + lift revealed on hover.
 *
 * Data comes from `features/organizations/demo-data.ts` (`getOrganizations()`), the same
 * demo-data-with-swap-point pattern as `features/investors` -- see that file for the swap point.
 */
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import { Link } from "@tanstack/react-router";
import { ArrowUpRight } from "lucide-react";
import { getOrganizations, type Organization } from "@/features/organizations/demo-data";

function OrgAvatar({ org, index }: { org: Organization; index: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.4, delay: index * 0.05, ease: [0.22, 1, 0.36, 1] }}
    >
      <Link
        to={org.to}
        className="group flex flex-col items-center gap-3 rounded-2xl px-3 py-2 text-center transition-all hover:-translate-y-1"
      >
        <div className="relative flex size-[76px] items-center justify-center overflow-hidden rounded-full border border-border bg-white p-1.5 shadow-soft grayscale transition-all duration-300 group-hover:grayscale-0 group-hover:shadow-glow sm:size-20">
          <div className="absolute inset-0 rounded-full opacity-0 ring-2 ring-primary/40 transition-opacity duration-300 group-hover:opacity-100" />
          <img src={org.logo} alt={org.name} className="size-full rounded-full object-cover" />
        </div>
        <div>
          <div className="max-w-[100px] truncate font-display text-[13px] font-semibold text-foreground/80 group-hover:text-foreground">
            {org.name}
          </div>
          <div className="mt-0.5 text-[10px] uppercase tracking-wider text-muted-foreground/70">
            {org.kind}
          </div>
        </div>
      </Link>
    </motion.div>
  );
}

export function OrganizationsCarousel() {
  const { t } = useTranslation();
  const [orgs, setOrgs] = useState<Organization[]>([]);

  useEffect(() => {
    getOrganizations().then(setOrgs);
  }, []);

  return (
    <section id="organizations" className="relative scroll-mt-24 px-6 py-16">
      <motion.div
        initial={{ opacity: 0, y: 24 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-80px" }}
        transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
        className="relative mx-auto max-w-6xl overflow-hidden rounded-[2rem] border border-border bg-card/60 px-8 py-14 shadow-elevated backdrop-blur-xl sm:px-12"
      >
        <div className="gradient-mesh absolute inset-0 opacity-25" aria-hidden />
        <div className="absolute inset-x-0 top-0 -z-0 h-1/2 bg-[radial-gradient(ellipse_at_top,oklch(0.75_0.16_275_/_0.14),transparent_70%)]" />

        <div className="relative text-center">
          <div className="inline-flex items-center gap-2 rounded-full border border-border bg-card/80 px-3 py-1 text-[11px] font-medium uppercase tracking-widest text-foreground/70 backdrop-blur">
            <span className="size-1.5 rounded-full bg-primary" />
            {t("organizations.eyebrow", { defaultValue: "Tasdiqlangan hamkorlar" })}
          </div>
          <h2 className="font-display mt-4 text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
            {t("organizations.title", { defaultValue: "Tashkilotlar va kompaniyalar" })}
          </h2>
          <p className="mx-auto mt-2 max-w-xl text-sm text-muted-foreground">
            {t("organizations.subtitle", {
              defaultValue: "Qurilish kompaniyalari, agentliklar, banklar va xizmat brendlari.",
            })}
          </p>

          <div className="mt-10 flex flex-wrap items-start justify-center gap-x-6 gap-y-6 sm:gap-x-10">
            {orgs.map((o, i) => (
              <OrgAvatar key={o.key} org={o} index={i} />
            ))}
          </div>

          <Link
            to="/list"
            className="group mt-10 inline-flex items-center gap-1.5 rounded-full border border-border bg-card/80 px-4 py-2 text-xs font-semibold text-foreground/80 backdrop-blur transition hover:border-primary/40 hover:text-foreground"
          >
            {t("organizations.cta", { defaultValue: "Hamkor sifatida qo'shiling" })}
            <ArrowUpRight className="size-3.5 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
          </Link>
        </div>
      </motion.div>
    </section>
  );
}
