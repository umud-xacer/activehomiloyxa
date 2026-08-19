/**
 * Bosqich 2 -- one `MainCategory`'s directory: a 3-column grid of its `SubCategory` cards, each
 * with its own banner (icon+gradient tile -- no per-subcategory photography exists, so a themed
 * tile stands in, same fallback convention as `catalog/CategoryTile.tsx`), name, and the list of
 * organizations that set that subcategory. Every subcategory in the sector renders (even with
 * zero organizations yet) so the taxonomy stays visible; clicking an organization goes to its
 * portfolio page (Bosqich 3, `/companies/$slug`).
 */
import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  Armchair,
  Blocks,
  Boxes,
  Building,
  Building2,
  Calculator,
  ChevronRight,
  Coins,
  Compass,
  Factory,
  Hammer,
  HardHat,
  Home,
  KeyRound,
  KeySquare,
  Landmark,
  Layers,
  Loader2,
  PaintRoller,
  PenTool,
  Ruler,
  Settings2,
  ShieldCheck,
  Shield,
  Sofa,
  Sparkles,
  TrafficCone,
  Trees,
  Wrench,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { Container } from "@/components/layout/Container";
import { useMediaAsset } from "@/lib/use-media-asset";
import {
  businessProfilesApi,
  mainCategoryBySlug,
  MAIN_CATEGORY_LABEL,
  MAIN_CATEGORY_DESCRIPTION,
  MAIN_CATEGORY_ACCENT,
  SUB_CATEGORIES_BY_MAIN_CATEGORY,
  SUB_CATEGORY_LABEL,
  SUB_CATEGORY_IMAGE,
  type BusinessProfile,
  type SubCategory,
} from "@/lib/business-profiles-client";

const SUB_CATEGORY_ICON: Record<SubCategory, LucideIcon> = {
  COMMERCIAL_BANK: Landmark,
  MORTGAGE_CENTER: KeyRound,
  MICROFINANCE: Coins,
  INSURANCE: Shield,
  LEASING: Building,
  GENERAL_CONTRACTOR: HardHat,
  SUBCONTRACTOR: Hammer,
  CIVIL_ENGINEERING: Ruler,
  RENOVATION_CONTRACTOR: PaintRoller,
  INFRASTRUCTURE_CONSTRUCTION: TrafficCone,
  BUILDING_MATERIALS_MANUFACTURER: Boxes,
  FURNITURE_MANUFACTURER: Armchair,
  METAL_PRODUCTS_MANUFACTURER: Factory,
  CONCRETE_CEMENT_MANUFACTURER: Blocks,
  GLASS_ALUMINUM_MANUFACTURER: Layers,
  ARCHITECTURE_STUDIO: Compass,
  INTERIOR_DESIGN_STUDIO: Sofa,
  LANDSCAPE_DESIGN_STUDIO: Trees,
  ENGINEERING_DESIGN_STUDIO: PenTool,
  HOME_REPAIR_SERVICE: Wrench,
  PLUMBING_ELECTRICAL_SERVICE: Zap,
  CLEANING_SERVICE: Sparkles,
  APPLIANCE_REPAIR_SERVICE: Settings2,
  RESIDENTIAL_AGENCY: Home,
  COMMERCIAL_AGENCY: Building,
  PROPERTY_MANAGEMENT: KeySquare,
  VALUATION_SERVICE: Calculator,
};

export const Route = createFileRoute("/organizations/$categorySlug")({
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

function OrgListItem({ profile }: { profile: BusinessProfile }) {
  const logo = useMediaAsset(profile.logoMediaAssetId);
  const name = profile.name.uz_latn || profile.name.ru || profile.name.en || "Tashkilot";

  const content = (
    <>
      <span className="flex size-9 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-border bg-white text-muted-foreground">
        {logo?.url ? (
          <img src={logo.url} alt="" className="size-full object-cover" />
        ) : (
          <Building2 className="size-4" />
        )}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium text-foreground">{name}</span>
        {profile.badge?.status === "VALID" && (
          <span className="inline-flex items-center gap-1 text-[11px] font-medium text-primary">
            <ShieldCheck className="size-3" /> Tasdiqlangan
          </span>
        )}
      </span>
    </>
  );

  if (!profile.slug) {
    return (
      <div className="flex items-center gap-3 rounded-xl px-2.5 py-2 opacity-70">{content}</div>
    );
  }

  return (
    <Link
      to="/companies/$slug"
      params={{ slug: profile.slug }}
      className="group flex items-center gap-3 rounded-xl px-2.5 py-2 transition hover:bg-muted"
    >
      {content}
      <ChevronRight className="size-4 shrink-0 text-muted-foreground/40 transition group-hover:translate-x-0.5 group-hover:text-muted-foreground" />
    </Link>
  );
}

function SubCategoryCard({
  subCategory,
  accent,
  orgs,
  index,
}: {
  subCategory: SubCategory;
  accent: string;
  orgs: BusinessProfile[];
  index: number;
}) {
  const Icon = SUB_CATEGORY_ICON[subCategory];
  const image = SUB_CATEGORY_IMAGE[subCategory];

  return (
    <motion.div
      initial={{ opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.4, delay: Math.min(index * 0.05, 0.4), ease: [0.22, 1, 0.36, 1] }}
      className="flex h-full flex-col overflow-hidden rounded-3xl border border-border bg-card shadow-soft"
    >
      {image ? (
        <div className="relative h-28 overflow-hidden">
          <img src={image} alt="" loading="lazy" className="size-full object-cover" />
          <div className="absolute inset-0 bg-gradient-to-t from-black/45 via-black/0 to-transparent" />
        </div>
      ) : (
        <div
          className="relative flex h-28 items-center justify-center"
          style={{ background: `linear-gradient(135deg, ${accent}33 0%, ${accent}0d 100%)` }}
        >
          <Icon className="size-10" style={{ color: accent }} strokeWidth={1.6} />
        </div>
      )}
      <div className="flex flex-1 flex-col p-4">
        <h3 className="font-display text-sm font-semibold text-foreground">
          {SUB_CATEGORY_LABEL[subCategory]}
        </h3>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {orgs.length > 0 ? `${orgs.length} ta tashkilot` : "Hozircha tashkilotlar yo'q"}
        </p>
        {orgs.length > 0 && (
          <div className="mt-3 divide-y divide-border/60 border-t border-border/60">
            {orgs.map((profile) => (
              <OrgListItem key={profile.id} profile={profile} />
            ))}
          </div>
        )}
      </div>
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
  const activeProfiles = profiles.filter((p) => p.subscriptionStatus === "ACTIVE");
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
                subCategory={subCategory}
                accent={accent}
                orgs={activeProfiles.filter((p) => p.subCategory === subCategory)}
                index={i}
              />
            ))}
          </div>
        )}
      </Container>
    </AppShell>
  );
}
