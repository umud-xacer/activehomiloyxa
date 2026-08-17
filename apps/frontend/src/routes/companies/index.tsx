import { useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Building2, Loader2, ShieldCheck } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/dashboard/EmptyState";
import { useMediaAsset } from "@/lib/use-media-asset";
import {
  businessProfilesApi,
  MAIN_CATEGORIES,
  MAIN_CATEGORY_LABEL,
  PROFILE_TYPE_LABEL,
  type BusinessProfile,
  type MainCategory,
} from "@/lib/business-profiles-client";

export const Route = createFileRoute("/companies/")({
  head: () => ({
    meta: [
      { title: "Tashkilotlar — ActiveHome" },
      {
        name: "description",
        content: "Qurilish, ta'mirlash va uy-joy sohasidagi tasdiqlangan tashkilotlar katalogi.",
      },
    ],
  }),
  component: Page,
});

function companyName(profile: BusinessProfile): string {
  return profile.name.uz_latn || profile.name.ru || profile.name.en || "Tashkilot";
}

/** Two-letter fallback avatar text -- first letter of the first two words, or the first two
 * characters of a single-word name (e.g. "Davr bank" -> "DB", "Anorbank" -> "AN"). */
function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase();
  return name.trim().slice(0, 2).toUpperCase();
}

function CompanyLogo({ profile }: { profile: BusinessProfile }) {
  const logo = useMediaAsset(profile.logoMediaAssetId);

  return (
    <div className="flex size-12 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-border bg-white p-1">
      {logo?.url ? (
        <img src={logo.url} alt={companyName(profile)} className="size-full object-contain" />
      ) : (
        <span className="font-display text-sm font-semibold text-primary">
          {initials(companyName(profile))}
        </span>
      )}
    </div>
  );
}

function CompanyCard({ profile, index }: { profile: BusinessProfile; index: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: Math.min(index * 0.05, 0.4), ease: [0.22, 1, 0.36, 1] }}
    >
      <Link
        to="/companies/$slug"
        params={{ slug: profile.slug || profile.id }}
        className="group flex h-full flex-col rounded-3xl border border-border bg-card p-6 shadow-soft transition hover:border-primary/40 hover:shadow-elevated"
      >
        <div className="flex items-center gap-3">
          <CompanyLogo profile={profile} />
          <div className="min-w-0">
            <p className="truncate font-display text-base font-semibold text-foreground">
              {companyName(profile)}
            </p>
            <p className="text-xs text-muted-foreground">
              {PROFILE_TYPE_LABEL[profile.profileType]}
            </p>
          </div>
        </div>
        {profile.description && (
          <p className="mt-3 line-clamp-2 text-sm text-muted-foreground">
            {profile.description.uz_latn || profile.description.ru || profile.description.en}
          </p>
        )}
        <div className="mt-4 flex flex-wrap items-center gap-2">
          {profile.badge?.status === "VALID" && (
            <span className="inline-flex w-fit items-center gap-1 rounded-full bg-success/10 px-2.5 py-1 text-[11px] font-semibold text-success">
              <ShieldCheck className="size-3.5" /> Tasdiqlangan
            </span>
          )}
          {profile.mainCategory && (
            <span className="inline-flex w-fit items-center rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-semibold text-primary">
              {MAIN_CATEGORY_LABEL[profile.mainCategory]}
            </span>
          )}
        </div>
      </Link>
    </motion.div>
  );
}

function CategoryTabs({
  selected,
  onSelect,
  counts,
}: {
  selected: MainCategory | null;
  onSelect: (value: MainCategory | null) => void;
  counts: Record<string, number>;
}) {
  return (
    <div className="-mx-6 mb-8 flex gap-2 overflow-x-auto px-6 pb-1 scrollbar-none">
      <button
        type="button"
        onClick={() => onSelect(null)}
        className={`shrink-0 rounded-full border px-4 py-2 text-sm font-semibold transition ${
          selected === null
            ? "border-primary bg-primary text-primary-foreground shadow-soft"
            : "border-border bg-card text-muted-foreground hover:border-primary/40 hover:text-foreground"
        }`}
      >
        Hammasi
      </button>
      {MAIN_CATEGORIES.map((value) => (
        <button
          key={value}
          type="button"
          onClick={() => onSelect(value)}
          className={`shrink-0 rounded-full border px-4 py-2 text-sm font-semibold transition ${
            selected === value
              ? "border-primary bg-primary text-primary-foreground shadow-soft"
              : "border-border bg-card text-muted-foreground hover:border-primary/40 hover:text-foreground"
          }`}
        >
          {MAIN_CATEGORY_LABEL[value]}
          {counts[value] ? <span className="ml-1.5 opacity-70">{counts[value]}</span> : null}
        </button>
      ))}
    </div>
  );
}

function Page() {
  const [selectedCategory, setSelectedCategory] = useState<MainCategory | null>(null);
  const { data: profiles, isLoading } = useQuery({
    queryKey: ["business-profiles", "public-directory"],
    queryFn: () => businessProfilesApi.listPublic(),
  });

  const active = (profiles ?? []).filter((p) => p.subscriptionStatus === "ACTIVE");
  const filtered = selectedCategory
    ? active.filter((p) => p.mainCategory === selectedCategory)
    : active;
  const counts = active.reduce<Record<string, number>>((acc, p) => {
    if (p.mainCategory) acc[p.mainCategory] = (acc[p.mainCategory] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <AppShell>
      <PageHeader
        eyebrow="Yuridik shaxslar uchun"
        title="Tashkilotlar"
        description="Qurilish materiallari, pudratchilar, dizaynerlar va xizmat ko'rsatuvchilarning tasdiqlangan katalogi."
      />
      {/* Narrower max-w-6xl base preserved on purpose (3-col directory grid reads better a bit
          tighter than the site's default 7xl) -- just extended so 1440px+ doesn't flatline. */}
      <div className="mx-auto max-w-6xl px-6 py-16 2xl:max-w-[1320px] 3xl:max-w-[1480px] 4xl:max-w-[1600px]">
        <CategoryTabs selected={selectedCategory} onSelect={setSelectedCategory} counts={counts} />
        {isLoading && (
          <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground">
            <Loader2 className="size-5 animate-spin" /> Yuklanmoqda…
          </div>
        )}
        {!isLoading && filtered.length === 0 && (
          <EmptyState
            icon={Building2}
            title="Hozircha tashkilot yo'q"
            description={
              selectedCategory
                ? "Bu kategoriyada hali tashkilot yo'q."
                : "Yaqinda faol obunaga ega tashkilotlar shu yerda ko'rinadi."
            }
          />
        )}
        {filtered.length > 0 && (
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {filtered.map((profile, i) => (
              <CompanyCard key={profile.id} profile={profile} index={i} />
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}
