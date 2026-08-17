/**
 * Homepage "Tashkilotlar" widget -- the top 5 verified/approved business profiles, in the same
 * ActiveHome card idiom as `PropertyCard`/`CompanyCard` (`rounded-3xl border border-border
 * bg-card shadow-soft`, fade-up on scroll), each linking straight to its real portfolio page
 * (`/companies/$slug`). Real data via `businessProfilesApi.listPublic({ verifiedOnly: true })`
 * -- replaces the previous avatar-carousel demo-data widget (Portfolio & Navigation UI spec).
 */
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import { Link } from "@tanstack/react-router";
import { ArrowUpRight, Building2, ShieldCheck } from "lucide-react";
import {
  businessProfilesApi,
  MAIN_CATEGORY_LABEL,
  PROFILE_TYPE_LABEL,
  type BusinessProfile,
} from "@/lib/business-profiles-client";
import { useMediaAsset } from "@/lib/use-media-asset";

function companyName(profile: BusinessProfile): string {
  return profile.name.uz_latn || profile.name.ru || profile.name.en || "Tashkilot";
}

function CompanyLogo({ profile }: { profile: BusinessProfile }) {
  const logo = useMediaAsset(profile.logoMediaAssetId);
  return (
    <div className="flex size-12 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-border bg-white p-1 shadow-soft">
      {logo?.url ? (
        <img src={logo.url} alt="" className="size-full object-contain" />
      ) : (
        <Building2 className="size-5 text-primary" />
      )}
    </div>
  );
}

function TopCompanyCard({ profile, index }: { profile: BusinessProfile; index: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.4, delay: Math.min(index * 0.06, 0.4), ease: [0.22, 1, 0.36, 1] }}
    >
      <Link
        to="/companies/$slug"
        params={{ slug: profile.slug || profile.id }}
        className="group flex h-full flex-col rounded-3xl border border-border bg-card p-5 shadow-soft transition hover:border-primary/40 hover:shadow-elevated"
      >
        <div className="flex items-center gap-3">
          <CompanyLogo profile={profile} />
          <div className="min-w-0">
            <p className="truncate font-display text-sm font-semibold text-foreground">
              {companyName(profile)}
            </p>
            <p className="truncate text-xs text-muted-foreground">
              {profile.mainCategory
                ? MAIN_CATEGORY_LABEL[profile.mainCategory]
                : PROFILE_TYPE_LABEL[profile.profileType]}
            </p>
          </div>
        </div>
        {profile.badge?.status === "VALID" && (
          <span className="mt-4 inline-flex w-fit items-center gap-1 rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-semibold text-primary">
            <ShieldCheck className="size-3.5" /> Tasdiqlangan
          </span>
        )}
      </Link>
    </motion.div>
  );
}

export function OrganizationsCarousel() {
  const { t } = useTranslation();
  const { data: profiles } = useQuery({
    queryKey: ["business-profiles", "public-directory"],
    queryFn: () => businessProfilesApi.listPublic({ verifiedOnly: true }),
  });

  const top5 = (profiles ?? []).filter((p) => p.subscriptionStatus === "ACTIVE").slice(0, 5);

  if (top5.length === 0) return null;

  return (
    <section id="organizations" className="relative scroll-mt-24 px-6 py-16">
      <motion.div
        initial={{ opacity: 0, y: 24 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-80px" }}
        transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
        className="relative mx-auto max-w-6xl overflow-hidden rounded-[2rem] border border-border bg-card/60 px-6 py-14 shadow-elevated backdrop-blur-xl sm:px-10"
      >
        <div className="gradient-mesh absolute inset-0 opacity-25" aria-hidden />
        <div className="absolute inset-x-0 top-0 -z-0 h-1/2 bg-[radial-gradient(ellipse_at_top,oklch(0.75_0.16_275_/_0.14),transparent_70%)]" />

        <div className="relative text-center">
          <div className="inline-flex items-center gap-2 rounded-full border border-border bg-card/80 px-3 py-1 text-[11px] font-medium uppercase tracking-widest text-foreground/70 backdrop-blur">
            <span className="size-1.5 rounded-full bg-primary" />
            {t("organizations.eyebrow", { defaultValue: "Tasdiqlangan hamkorlar" })}
          </div>
          <h2 className="font-display mt-4 text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
            {t("organizations.title", { defaultValue: "Tashkilotlar" })}
          </h2>
          <p className="mx-auto mt-2 max-w-xl text-sm text-muted-foreground">
            {t("organizations.subtitle", {
              defaultValue:
                "Qurilish, agentlik, bank va xizmat sohasidagi tasdiqlangan tashkilotlar — bitta ekotizimda.",
            })}
          </p>

          <div className="mt-10 grid grid-cols-1 gap-4 text-left sm:grid-cols-2 lg:grid-cols-5">
            {top5.map((profile, i) => (
              <TopCompanyCard key={profile.id} profile={profile} index={i} />
            ))}
          </div>

          <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
            <Link
              to="/companies"
              className="group inline-flex items-center gap-1.5 rounded-full bg-primary px-5 py-2.5 text-xs font-semibold text-primary-foreground shadow-soft transition hover:shadow-glow"
            >
              {t("organizations.view_all", { defaultValue: "Barcha tashkilotlarni ko'rish" })}
              <ArrowUpRight className="size-3.5 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
            </Link>
            <Link
              to="/list"
              className="group inline-flex items-center gap-1.5 rounded-full border border-border bg-card/80 px-4 py-2 text-xs font-semibold text-foreground/80 backdrop-blur transition hover:border-primary/40 hover:text-foreground"
            >
              {t("organizations.cta", { defaultValue: "Hamkor sifatida qo'shiling" })}
              <ArrowUpRight className="size-3.5 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
            </Link>
          </div>
        </div>
      </motion.div>
    </section>
  );
}
