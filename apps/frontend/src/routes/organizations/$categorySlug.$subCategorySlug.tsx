/**
 * Bosqich 3 -- one `SubCategory`'s organizations directory: every ACTIVE-subscription business
 * profile set to this exact sub-category, as a 3-column card grid, with a name/brand search box
 * scoped to just this list. Deliberately shows no category/subcategory navigation of its own
 * (Bosqich 1/2 already did that) -- this page's entire job is "organizations in this one
 * sub-category, nothing else."
 */
import { useMemo, useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Loader2, MapPin, Phone, Search } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { Container } from "@/components/layout/Container";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/state/EmptyState";
import { useMediaAsset } from "@/lib/use-media-asset";
import {
  businessProfilesApi,
  mainCategoryBySlug,
  subCategoryBySlug,
  MAIN_CATEGORY_LABEL,
  MAIN_CATEGORY_ACCENT,
  SUB_CATEGORY_LABEL,
  SUB_CATEGORY_IMAGE,
  SUB_CATEGORY_ICON,
  ORGANIZATION_PLACEHOLDER_ICON,
  VERIFIED_BADGE_ICON,
  type BusinessProfile,
} from "@/lib/business-profiles-client";

export const Route = createFileRoute("/organizations/$categorySlug/$subCategorySlug")({
  head: ({ params }) => {
    const category = mainCategoryBySlug(params.categorySlug);
    const subCategory = category ? subCategoryBySlug(category, params.subCategorySlug) : null;
    return {
      meta: [
        {
          title: subCategory
            ? `${SUB_CATEGORY_LABEL[subCategory]} — Tashkilotlar — ActiveHome`
            : "Tashkilotlar — ActiveHome",
        },
      ],
    };
  },
  component: Page,
});

function profileName(profile: BusinessProfile): string {
  return profile.name.uz_latn || profile.name.ru || profile.name.en || "Tashkilot";
}

function OrganizationCard({ profile, index }: { profile: BusinessProfile; index: number }) {
  const logo = useMediaAsset(profile.logoMediaAssetId);
  const name = profileName(profile);
  const description =
    profile.description?.uz_latn || profile.description?.ru || profile.description?.en || "";
  const phone = profile.contacts?.phones?.[0];
  const PlaceholderIcon = ORGANIZATION_PLACEHOLDER_ICON;
  const VerifiedIcon = VERIFIED_BADGE_ICON;
  const verified = profile.badge?.status === "VALID";

  const card = (
    <motion.div
      initial={{ opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.4, delay: Math.min(index * 0.05, 0.4), ease: [0.22, 1, 0.36, 1] }}
      className="group flex h-full flex-col rounded-3xl border border-border bg-card p-5 shadow-soft transition hover:-translate-y-0.5 hover:shadow-lg"
    >
      <div className="flex items-start gap-3">
        <span className="flex size-14 shrink-0 items-center justify-center overflow-hidden rounded-2xl border border-border bg-white text-muted-foreground">
          {logo?.url ? (
            <img src={logo.url} alt="" className="size-full object-cover" />
          ) : (
            <PlaceholderIcon className="size-6" />
          )}
        </span>
        <div className="min-w-0 pt-1">
          <h3 className="font-display truncate text-base font-semibold text-foreground">{name}</h3>
          {verified && (
            <span className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-primary">
              <VerifiedIcon className="size-3.5" /> Tasdiqlangan
            </span>
          )}
        </div>
      </div>

      {description && (
        <p className="mt-3 line-clamp-2 text-sm text-muted-foreground">{description}</p>
      )}

      <div className="mt-4 space-y-1.5 text-sm text-muted-foreground">
        {phone && (
          <div className="flex items-center gap-2">
            <Phone className="size-3.5 shrink-0" />
            <span className="truncate">{phone}</span>
          </div>
        )}
        {profile.address && (
          <div className="flex items-center gap-2">
            <MapPin className="size-3.5 shrink-0" />
            <span className="truncate">{profile.address}</span>
          </div>
        )}
      </div>

      <div className="mt-4 pt-1">
        <span className="inline-flex items-center text-sm font-medium text-primary transition group-hover:underline">
          Portfolioni ko'rish →
        </span>
      </div>
    </motion.div>
  );

  if (!profile.slug) return card;

  return (
    <Link
      to="/companies/$slug"
      params={{ slug: profile.slug }}
      className="block h-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background rounded-3xl"
    >
      {card}
    </Link>
  );
}

function Page() {
  const { categorySlug, subCategorySlug } = Route.useParams();
  const category = mainCategoryBySlug(categorySlug);
  const subCategory = category ? subCategoryBySlug(category, subCategorySlug) : null;
  const [query, setQuery] = useState("");

  const { data: profiles = [], isLoading } = useQuery({
    queryKey: ["business-profiles", "sub-category", subCategory],
    queryFn: () => businessProfilesApi.listPublic({ subCategory: subCategory! }),
    enabled: !!subCategory,
  });

  const activeProfiles = useMemo(
    () => profiles.filter((p) => p.subscriptionStatus === "ACTIVE"),
    [profiles],
  );

  const filteredProfiles = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return activeProfiles;
    return activeProfiles.filter((p) => profileName(p).toLowerCase().includes(q));
  }, [activeProfiles, query]);

  if (!category || !subCategory) {
    return (
      <AppShell>
        <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 pt-32 text-center">
          <p className="font-display text-xl font-semibold">Bo'lim topilmadi</p>
          <Link to="/organizations" className="text-sm text-primary hover:underline">
            Tashkilotlar bo'limiga qaytish
          </Link>
        </div>
      </AppShell>
    );
  }

  const accent = MAIN_CATEGORY_ACCENT[category];

  return (
    <AppShell>
      <PageHeader
        eyebrow="Tashkilotlar"
        title={SUB_CATEGORY_LABEL[subCategory]}
        description={
          activeProfiles.length > 0
            ? `${MAIN_CATEGORY_LABEL[category]} yo'nalishida ${activeProfiles.length} ta tasdiqlangan tashkilot`
            : `${MAIN_CATEGORY_LABEL[category]} yo'nalishidagi tashkilotlar`
        }
        accentColor={accent}
        backgroundImageUrl={SUB_CATEGORY_IMAGE[subCategory]}
        icon={SUB_CATEGORY_ICON[subCategory]}
        backTo={`/organizations/${categorySlug}`}
        backLabel="Kategoriyalarga qaytish"
        crumbs={[
          { label: "Bosh sahifa", to: "/" },
          { label: "Tashkilotlar", to: "/organizations" },
          { label: MAIN_CATEGORY_LABEL[category], to: `/organizations/${categorySlug}` },
          { label: SUB_CATEGORY_LABEL[subCategory] },
        ]}
      />
      <Container wide className="py-10">
        {isLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Yuklanmoqda…
          </div>
        ) : (
          <>
            {activeProfiles.length > 0 && (
              <div className="relative mb-6 max-w-sm">
                <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Nomi bo'yicha qidirish..."
                  className="pl-9"
                />
              </div>
            )}

            {activeProfiles.length === 0 ? (
              <EmptyState
                icon={SUB_CATEGORY_ICON[subCategory]}
                title="Hozircha ushbu subkategoriyada birorta ham tashkilot ro'yxatdan o'tmagan"
                description="Yaqin orada bu yerda tasdiqlangan tashkilotlar paydo bo'ladi."
                action={
                  <Button asChild variant="outline">
                    <Link to="/organizations/$categorySlug" params={{ categorySlug }}>
                      Boshqa subkategoriyalarni ko'rish
                    </Link>
                  </Button>
                }
              />
            ) : filteredProfiles.length === 0 ? (
              <EmptyState
                icon={Search}
                title="Hech narsa topilmadi"
                description={`"${query}" bo'yicha tashkilot topilmadi. Boshqa nom bilan qidirib ko'ring.`}
              />
            ) : (
              <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
                {filteredProfiles.map((profile, i) => (
                  <OrganizationCard key={profile.id} profile={profile} index={i} />
                ))}
              </div>
            )}
          </>
        )}
      </Container>
    </AppShell>
  );
}
