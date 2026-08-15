import { useEffect, useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  Building2,
  Gauge,
  Loader2,
  Save,
  Phone,
  Mail,
  Globe,
  MapPin,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Wrench,
  ExternalLink,
  Plus,
} from "lucide-react";
import { requireOnboardedLegalEntity } from "@/lib/require-auth";
import { DashboardShell } from "@/components/layout/DashboardShell";
import { SectionCard } from "@/components/dashboard/SectionCard";
import { EmptyState } from "@/components/dashboard/EmptyState";
import { TextListField } from "@/components/business-profile/TextListField";
import { BrandingSection } from "@/components/business-profile/BrandingSection";
import { PortfolioGallery } from "@/components/business-profile/PortfolioGallery";
import { PromoVideoSection } from "@/components/business-profile/PromoVideoUpload";
import { LandingPreviewCard, type ProfileDraft } from "@/components/business-profile/LandingPreviewCard";
import { useMe } from "@/features/auth/useAuth";
import { ApiError, http } from "@/lib/http";
import {
  businessProfilesApi,
  PROFILE_TYPE_LABEL,
  type BusinessProfile,
  type PortfolioItem,
} from "@/lib/business-profiles-client";

interface SearchHitLite {
  listingId: string;
  title: string;
  price?: { amount: string; currency: string } | null;
  slug?: string | null;
}

export const Route = createFileRoute("/dashboard/business-profile")({
  beforeLoad: requireOnboardedLegalEntity,
  head: () => ({
    meta: [
      { title: "Biznes profil — ActiveHome" },
      { name: "description", content: "Kompaniya ma'lumotlari, aloqa va portfolio galereyasi." },
    ],
  }),
  component: Page,
});

function useOwnedProfiles(ownedProfileIds: string[]) {
  return useQuery({
    queryKey: ["business-profiles", "mine", ownedProfileIds],
    queryFn: () => Promise.all(ownedProfileIds.map((id) => businessProfilesApi.get(id))),
    enabled: ownedProfileIds.length > 0,
  });
}

function draftFromProfile(profile: BusinessProfile): ProfileDraft {
  return {
    name: profile.name.uz_latn || "",
    description: profile.description?.uz_latn || "",
    address: profile.address || "",
    phones: profile.contacts?.phones ?? [],
    emails: profile.contacts?.emails ?? [],
    website: profile.contacts?.website || "",
  };
}

/** Same 7 fields the mandatory onboarding wizard (`routes/organization/setup.tsx`) treats as
 * landing-page essentials, checked against live (unsaved) draft state for the text fields and
 * against saved `profile` state for media (branding/portfolio only change via their own
 * immediate-save upload flows, never through the "Saqlash" button). `portfolioCount` is passed
 * in separately -- `BusinessProfile.portfolio` is never populated by the profile-read endpoint,
 * only the dedicated `listPortfolio` call returns items (see `PortfolioGallery`'s
 * `onItemsChange`). */
function completeness(profile: BusinessProfile, draft: ProfileDraft, portfolioCount: number) {
  const checks = [
    { label: "Kompaniya nomi", done: !!draft.name.trim() },
    { label: "Tavsif", done: !!draft.description.trim() },
    { label: "Manzil", done: !!draft.address.trim() },
    { label: "Telefon yoki email", done: draft.phones.some((p) => p.trim()) || draft.emails.some((e) => e.trim()) },
    { label: "Logotip", done: !!profile.logoMediaAssetId },
    { label: "Muqova rasmi", done: !!profile.bannerMediaAssetId },
    { label: "Portfolio (rasm/video)", done: portfolioCount > 0 },
  ];
  const missing = checks.filter((c) => !c.done).map((c) => c.label);
  return { percent: Math.round(((checks.length - missing.length) / checks.length) * 100), missing };
}

function ProfileCompletionMeter({
  profile,
  draft,
  portfolioCount,
}: {
  profile: BusinessProfile;
  draft: ProfileDraft;
  portfolioCount: number;
}) {
  const { percent, missing } = completeness(profile, draft, portfolioCount);
  const complete = percent === 100;

  return (
    <div className="rounded-2xl border border-border bg-card p-5 shadow-soft">
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <div
            className={`flex size-9 shrink-0 items-center justify-center rounded-xl ${
              complete ? "bg-success/15 text-success" : "bg-primary/10 text-primary"
            }`}
          >
            {complete ? <Sparkles className="size-4" /> : <Gauge className="size-4" />}
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-foreground">Profil to'liqligi</p>
            <p className="truncate text-xs text-muted-foreground">
              {complete
                ? "Landing sahifangiz to'liq tayyor."
                : `Yana: ${missing.slice(0, 2).join(", ")}${missing.length > 2 ? ` va yana ${missing.length - 2}` : ""}`}
            </p>
          </div>
        </div>
        <span className="font-display text-lg font-semibold text-foreground">{percent}%</span>
      </div>
      <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${percent}%` }}
          transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
          className={`h-full rounded-full ${complete ? "bg-success" : "bg-primary"}`}
        />
      </div>
    </div>
  );
}

function SubscriptionBanner({ profile }: { profile: BusinessProfile }) {
  const active = profile.subscriptionStatus === "ACTIVE";
  return (
    <div
      className={`flex flex-wrap items-center justify-between gap-4 rounded-3xl border p-6 shadow-soft ${
        active ? "border-success/30 bg-success/5" : "border-warning/30 bg-warning/5"
      }`}
    >
      <div className="flex items-center gap-4">
        <div
          className={`flex size-11 shrink-0 items-center justify-center rounded-2xl ${
            active ? "bg-success/15 text-success" : "bg-warning/15 text-warning"
          }`}
        >
          {active ? <ShieldCheck className="size-5" /> : <ShieldAlert className="size-5" />}
        </div>
        <div>
          <p className="font-display text-base font-semibold text-foreground">
            {active
              ? "Obuna faol"
              : profile.subscriptionStatus === "EXPIRED"
                ? "Obuna muddati tugagan"
                : "Obuna mavjud emas"}
          </p>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {active && profile.subscriptionValidUntil
              ? `${new Date(profile.subscriptionValidUntil).toLocaleDateString("uz-UZ")} sanasigacha amal qiladi.`
              : "Profilingiz va e'lonlaringiz ommaviy katalogda ko'rinishi uchun obuna faol bo'lishi kerak."}
          </p>
        </div>
      </div>
      {!active && (
        <Link
          to="/subscriptions"
          className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90"
        >
          Obunani yangilash
        </Link>
      )}
    </div>
  );
}

function ServicesSection({ profileId }: { profileId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["search", "owner-profile", profileId],
    queryFn: () =>
      http.get<{ items: SearchHitLite[] }>("/search", {
        params: { ownerProfileId: profileId, limit: 20 },
      }),
  });

  return (
    <SectionCard
      title="Xizmatlarim va e'lonlarim"
      icon={Wrench}
      description="Ushbu profil nomidan joylashtirilgan e'lonlar."
      index={4}
      action={
        <Link
          to="/list"
          className="inline-flex items-center gap-1.5 rounded-full bg-primary px-3.5 py-1.5 text-xs font-semibold text-primary-foreground transition hover:shadow-glow"
        >
          <Plus className="size-3.5" /> Yangi e'lon
        </Link>
      }
    >
      {isLoading ? (
        <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Yuklanmoqda…
        </div>
      ) : !data || data.items.length === 0 ? (
        <EmptyState
          icon={Wrench}
          title="Hali e'lon joylashtirilmagan"
          description="Birinchi xizmat yoki mahsulotingizni qo'shing."
        />
      ) : (
        <ul className="divide-y divide-border/70">
          {data.items.map((item) => (
            <li key={item.listingId} className="flex items-center justify-between gap-4 py-3">
              <span className="text-sm font-medium text-foreground">{item.title}</span>
              <div className="flex items-center gap-3">
                {item.price && (
                  <span className="text-sm text-muted-foreground">
                    {Number(item.price.amount).toLocaleString("uz-UZ")} {item.price.currency}
                  </span>
                )}
                {item.slug && (
                  <Link
                    to="/list/$listingId"
                    params={{ listingId: item.slug }}
                    className="text-muted-foreground transition hover:text-primary"
                  >
                    <ExternalLink className="size-4" />
                  </Link>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}

function ProfileForm({
  profile,
  draft,
  onDraftChange,
}: {
  profile: BusinessProfile;
  draft: ProfileDraft;
  onDraftChange: (next: ProfileDraft) => void;
}) {
  const queryClient = useQueryClient();
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const patch = (next: Partial<ProfileDraft>) => onDraftChange({ ...draft, ...next });

  const onSave = async () => {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      await businessProfilesApi.update(profile.id, {
        name: draft.name,
        description: draft.description,
        address: draft.address,
        contacts: {
          phones: draft.phones.map((p) => p.trim()).filter(Boolean),
          emails: draft.emails.map((e) => e.trim()).filter(Boolean),
          website: draft.website.trim() || undefined,
        },
      });
      await queryClient.invalidateQueries({ queryKey: ["business-profiles"] });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Saqlab bo'lmadi.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <SectionCard
      title="Kompaniya ma'lumotlari"
      icon={Building2}
      description="O'ngdagi (yoki pastdagi) jonli ko'rinish har bir o'zgarishni darhol aks ettiradi."
      index={1}
    >
      <div className="space-y-5">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label className="text-xs font-medium text-muted-foreground">Kompaniya nomi *</label>
            <input
              value={draft.name}
              onChange={(e) => patch({ name: e.target.value })}
              className="mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm outline-none transition focus:ring-2 focus:ring-primary/30"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Yo'nalishi</label>
            <div className="mt-1 flex h-[38px] items-center rounded-xl border border-border bg-muted px-3 text-sm text-muted-foreground">
              {PROFILE_TYPE_LABEL[profile.profileType]}
            </div>
          </div>
        </div>

        <div>
          <label className="text-xs font-medium text-muted-foreground">Tavsif</label>
          <textarea
            value={draft.description}
            onChange={(e) => patch({ description: e.target.value })}
            rows={3}
            placeholder="Kompaniyangiz haqida qisqacha ma'lumot"
            className="mt-1 w-full resize-none rounded-xl border border-border bg-background px-3 py-2 text-sm outline-none transition focus:ring-2 focus:ring-primary/30"
          />
        </div>

        <div>
          <label className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
            <MapPin className="size-3.5" /> Manzil
          </label>
          <input
            value={draft.address}
            onChange={(e) => patch({ address: e.target.value })}
            placeholder="Shahar, tuman, ko'cha"
            className="mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm outline-none transition focus:ring-2 focus:ring-primary/30"
          />
        </div>

        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          <TextListField
            icon={Phone}
            label="Telefon raqamlari"
            placeholder="+998 90 123 45 67"
            values={draft.phones}
            onChange={(phones) => patch({ phones })}
          />
          <TextListField
            icon={Mail}
            label="Email manzillari"
            placeholder="info@company.uz"
            values={draft.emails}
            onChange={(emails) => patch({ emails })}
          />
        </div>

        <div>
          <label className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
            <Globe className="size-3.5" /> Veb-sayt
          </label>
          <input
            value={draft.website}
            onChange={(e) => patch({ website: e.target.value })}
            placeholder="https://company.uz"
            className="mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm outline-none transition focus:ring-2 focus:ring-primary/30"
          />
        </div>

        {error && <p className="text-xs text-destructive">{error}</p>}

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onSave}
            disabled={saving || !draft.name.trim()}
            className="inline-flex items-center gap-2 rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground shadow-soft transition hover:shadow-glow disabled:opacity-60"
          >
            {saving ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
            Saqlash
          </button>
          {saved && <span className="text-xs font-medium text-success">Saqlandi.</span>}
        </div>
      </div>
    </SectionCard>
  );
}

function BusinessProfilePageContent({
  account,
}: {
  account: NonNullable<ReturnType<typeof useMe>["data"]>;
}) {
  const ownedProfileIds = account.ownedProfileIds ?? [];
  const { data: profiles, isLoading } = useOwnedProfiles(ownedProfileIds);
  const profile = profiles?.[0];

  // Seeded once from the loaded profile, then owned by the form/preview pair below -- lets the
  // preview card reflect keystrokes instantly instead of only after "Saqlash" round-trips.
  const [draft, setDraft] = useState<ProfileDraft | null>(null);
  useEffect(() => {
    if (profile && !draft) setDraft(draftFromProfile(profile));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile]);

  // `BusinessProfile.portfolio` is never populated by the profile-read endpoint -- PortfolioGallery
  // reports the live list via this callback instead (see its own docstring).
  const [portfolioItems, setPortfolioItems] = useState<PortfolioItem[]>([]);

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-8 lg:px-8">
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
        className="relative overflow-hidden rounded-3xl border border-border bg-card p-8 shadow-soft"
      >
        <div className="gradient-mesh absolute inset-0 -z-10 opacity-70" />
        <h1 className="font-display text-3xl font-semibold tracking-tight">Biznes profil</h1>
        <p className="mt-2 max-w-xl text-sm text-muted-foreground">
          Bu yerda to'ldirgan har bir ma'lumot — o'zingizning ActiveHome ichidagi shaxsiy landing
          sahifangiz. To'ldirgan sari o'ngdagi jonli ko'rinishda o'zgarishlarni darhol ko'rasiz.
        </p>
      </motion.div>

      {ownedProfileIds.length === 0 ? (
        <SectionCard title="Biznes profil topilmadi" icon={Building2} index={0}>
          <p className="text-sm text-muted-foreground">
            Avval{" "}
            <Link to="/dashboard/seller" className="font-semibold text-primary hover:underline">
              boshqaruv panelida
            </Link>{" "}
            biznes profilingizni yarating.
          </p>
        </SectionCard>
      ) : isLoading || !profile || !draft ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Yuklanmoqda…
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3 lg:items-start">
          <div className="order-2 space-y-6 lg:order-1 lg:col-span-2">
            <ProfileCompletionMeter profile={profile} draft={draft} portfolioCount={portfolioItems.length} />
            <SubscriptionBanner profile={profile} />
            <ProfileForm profile={profile} draft={draft} onDraftChange={setDraft} />
            <BrandingSection profile={profile} />
            <PortfolioGallery profile={profile} onItemsChange={setPortfolioItems} />
            <PromoVideoSection profile={profile} />
            <ServicesSection profileId={profile.id} />
          </div>
          <div className="order-1 lg:sticky lg:top-24 lg:order-2">
            <p className="mb-2 flex items-center gap-1.5 px-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Ommaviy sahifa ko'rinishi
            </p>
            <LandingPreviewCard profile={profile} draft={draft} portfolio={portfolioItems} />
          </div>
        </div>
      )}
    </div>
  );
}

function Page() {
  const { data: account } = useMe();
  if (!account) return null;

  return (
    <DashboardShell account={account}>
      <BusinessProfilePageContent account={account} />
    </DashboardShell>
  );
}
