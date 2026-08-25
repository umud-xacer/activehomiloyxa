/**
 * Bosqich 2 -- one `MainCategory`'s directory: a 3-column grid of its `SubCategory` cards, each
 * with its own banner (icon+gradient tile -- no per-subcategory photography exists, so a themed
 * tile stands in, same fallback convention as `catalog/CategoryTile.tsx`), name, and organization
 * count. Every subcategory in the sector renders (even with zero organizations yet) so the
 * taxonomy stays visible; clicking a card drills into Bosqich 3
 * (`/organizations/$categorySlug/$subCategorySlug`), the dedicated organizations directory for
 * that one sub-category -- this page itself never lists individual organizations.
 */
import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useState } from "react";
import { ChevronRight, Loader2 } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { Container } from "@/components/layout/Container";
import {
  businessProfilesApi,
  mainCategoryBySlug,
  MAIN_CATEGORY_LABEL,
  MAIN_CATEGORY_DESCRIPTION,
  MAIN_CATEGORY_ACCENT,
  SUB_CATEGORIES_BY_MAIN_CATEGORY,
  SUB_CATEGORY_LABEL,
  SUB_CATEGORY_IMAGE,
  SUB_CATEGORY_ICON,
  SUB_CATEGORY_SLUG,
  type BusinessProfile,
  type SubCategory,
} from "@/lib/business-profiles-client";

export const Route = createFileRoute("/organizations/$categorySlug/")({
  head: ({ params }) => {
    const category = mainCategoryBySlug(params.categorySlug);
    return {
      meta: [
        {
          title: category
            ? `${MAIN_CATEGORY_LABEL[category]} — Tashkilotlar — ActiveHome`
            : "Tashkilotlar — ActiveHome",
        },
      ],
    };
  },
  component: Page,
});

function SubCategoryCard({
  categorySlug,
  subCategory,
  accent,
  count,
  index,
}: {
  categorySlug: string;
  subCategory: SubCategory;
  accent: string;
  count: number;
  index: number;
}) {
  const Icon = SUB_CATEGORY_ICON[subCategory];
  const image = SUB_CATEGORY_IMAGE[subCategory];
  // A `SUB_CATEGORY_IMAGE` entry is a real URL, but the keyless third-party photo source it
  // points at (loremflickr, see that const's own docstring) can 500/404 at request time even
  // when the URL itself is well-formed -- confirmed live for several sub-categories. Track load
  // failure so the card falls back to the SAME accent-gradient+icon tile the "no photo yet"
  // branch already uses, instead of silently rendering nothing but the dark overlay.
  const [imgFailed, setImgFailed] = useState(false);
  const showImage = !!image && !imgFailed;

  return (
    <motion.div
      initial={{ opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.4, delay: Math.min(index * 0.05, 0.4), ease: [0.22, 1, 0.36, 1] }}
    >
      <Link
        to="/organizations/$categorySlug/$subCategorySlug"
        params={{ categorySlug, subCategorySlug: SUB_CATEGORY_SLUG[subCategory] }}
        className="group relative flex h-40 flex-col justify-end overflow-hidden rounded-3xl border border-border shadow-soft transition-all duration-300 hover:-translate-y-1.5 hover:shadow-elevated"
      >
        {showImage ? (
          <img
            src={image}
            alt=""
            loading="lazy"
            onError={() => setImgFailed(true)}
            className="absolute inset-0 size-full object-cover transition-transform duration-500 group-hover:scale-105"
          />
        ) : (
          <div
            className="absolute inset-0"
            style={{ background: `linear-gradient(135deg, ${accent}55 0%, ${accent}14 100%)` }}
          />
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/40 to-transparent" />
        {!showImage && (
          <Icon
            className="absolute right-4 top-4 size-9 text-white/25"
            strokeWidth={1.5}
            aria-hidden
          />
        )}
        <div className="relative flex items-center justify-between gap-3 p-4">
          <div className="min-w-0">
            <h3 className="font-display text-sm font-semibold text-white drop-shadow-sm">
              {SUB_CATEGORY_LABEL[subCategory]}
            </h3>
            <p className="mt-0.5 text-xs text-white/80">
              {count > 0 ? `${count} ta tashkilot` : "Hozircha tashkilotlar yo'q"}
            </p>
          </div>
          <ChevronRight className="size-4 shrink-0 text-white/70 transition group-hover:translate-x-0.5 group-hover:text-white" />
        </div>
      </Link>
    </motion.div>
  );
}

function Page() {
  const { categorySlug } = Route.useParams();
  const category = mainCategoryBySlug(categorySlug);

  const { data: profiles = [], isLoading } = useQuery({
    queryKey: ["business-profiles", "main-category", category],
    queryFn: () => businessProfilesApi.listPublic({ mainCategory: category! }),
    enabled: !!category,
  });

  if (!category) {
    return (
      <AppShell>
        <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 pt-32 text-center">
          <p className="font-display text-xl font-semibold">Kategoriya topilmadi</p>
          <Link to="/organizations" className="text-sm text-primary hover:underline">
            Tashkilotlar bo'limiga qaytish
          </Link>
        </div>
      </AppShell>
    );
  }

  const accent = MAIN_CATEGORY_ACCENT[category];
  const activeProfiles: BusinessProfile[] = profiles.filter(
    (p) => p.subscriptionStatus === "ACTIVE",
  );
  const subCategories = SUB_CATEGORIES_BY_MAIN_CATEGORY[category];

  return (
    <AppShell>
      <PageHeader
        eyebrow="Tashkilotlar"
        title={MAIN_CATEGORY_LABEL[category]}
        description={MAIN_CATEGORY_DESCRIPTION[category]}
        accentColor={accent}
        crumbs={[
          { label: "Bosh sahifa", to: "/" },
          { label: "Tashkilotlar", to: "/organizations" },
          { label: MAIN_CATEGORY_LABEL[category] },
        ]}
      />
      <Container wide className="py-10">
        {isLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Yuklanmoqda…
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {subCategories.map((subCategory, i) => (
              <SubCategoryCard
                key={subCategory}
                categorySlug={categorySlug}
                subCategory={subCategory}
                accent={accent}
                count={activeProfiles.filter((p) => p.subCategory === subCategory).length}
                index={i}
              />
            ))}
          </div>
        )}
      </Container>
    </AppShell>
  );
}
