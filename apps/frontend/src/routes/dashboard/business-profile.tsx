import { useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  Building2,
  Loader2,
  Save,
  Phone,
  Mail,
  Globe,
  MapPin,
  ShieldAlert,
  ShieldCheck,
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
import { useMe } from "@/features/auth/useAuth";
import { ApiError, http } from "@/lib/http";
import {
  businessProfilesApi,
  PROFILE_TYPE_LABEL,
  type BusinessProfile,
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
      index={3}
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

function ProfileForm({ profile }: { profile: BusinessProfile }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(profile.name.uz_latn || "");
  const [description, setDescription] = useState(profile.description?.uz_latn || "");
  const [phones, setPhones] = useState<string[]>(profile.contacts?.phones ?? []);
  const [emails, setEmails] = useState<string[]>(profile.contacts?.emails ?? []);
  const [website, setWebsite] = useState(profile.contacts?.website || "");
  const [address, setAddress] = useState(profile.address || "");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSave = async () => {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      await businessProfilesApi.update(profile.id, {
        name,
        description,
        address,
        contacts: {
          phones: phones.map((p) => p.trim()).filter(Boolean),
          emails: emails.map((e) => e.trim()).filter(Boolean),
          website: website.trim() || undefined,
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
    <SectionCard title="Kompaniya ma'lumotlari" icon={Building2} index={0}>
      <div className="space-y-5">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label className="text-xs font-medium text-muted-foreground">Kompaniya nomi *</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
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
            value={description}
            onChange={(e) => setDescription(e.target.value)}
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
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            placeholder="Shahar, tuman, ko'cha"
            className="mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm outline-none transition focus:ring-2 focus:ring-primary/30"
          />
        </div>

        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          <TextListField
            icon={Phone}
            label="Telefon raqamlari"
            placeholder="+998 90 123 45 67"
            values={phones}
            onChange={setPhones}
          />
          <TextListField
            icon={Mail}
            label="Email manzillari"
            placeholder="info@company.uz"
            values={emails}
            onChange={setEmails}
          />
        </div>

        <div>
          <label className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
            <Globe className="size-3.5" /> Veb-sayt
          </label>
          <input
            value={website}
            onChange={(e) => setWebsite(e.target.value)}
            placeholder="https://company.uz"
            className="mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm outline-none transition focus:ring-2 focus:ring-primary/30"
          />
        </div>

        {error && <p className="text-xs text-destructive">{error}</p>}

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onSave}
            disabled={saving || !name}
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

  return (
    <div className="mx-auto max-w-4xl space-y-8 px-4 py-8 lg:px-8">
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
        className="relative overflow-hidden rounded-3xl border border-border bg-card p-8 shadow-soft"
      >
        <div className="gradient-mesh absolute inset-0 -z-10 opacity-70" />
        <h1 className="font-display text-3xl font-semibold tracking-tight">Biznes profil</h1>
        <p className="mt-2 max-w-xl text-sm text-muted-foreground">
          Landing page — kompaniyangiz ommaviy sahifada shu ma'lumotlar bilan ko'rinadi.
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
      ) : isLoading || !profile ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Yuklanmoqda…
        </div>
      ) : (
        <>
          <SubscriptionBanner profile={profile} />
          <ProfileForm profile={profile} />
          <BrandingSection profile={profile} />
          <PortfolioGallery profile={profile} />
          <ServicesSection profileId={profile.id} />
        </>
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
