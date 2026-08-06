import { useEffect, useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  Building2,
  Loader2,
  Save,
  Plus,
  X,
  Phone,
  Mail,
  Globe,
  MapPin,
  ImagePlus,
  Trash2,
  Film,
  ShieldAlert,
  ShieldCheck,
  Image as ImageIcon,
  Wrench,
  ExternalLink,
} from "lucide-react";
import { requireAuth } from "@/lib/require-auth";
import { DashboardShell } from "@/components/layout/DashboardShell";
import { SectionCard } from "@/components/dashboard/SectionCard";
import { EmptyState } from "@/components/dashboard/EmptyState";
import { useMe } from "@/features/auth/useAuth";
import { ApiError, http } from "@/lib/http";
import {
  businessProfilesApi,
  PROFILE_TYPE_LABEL,
  type BusinessProfile,
  type PortfolioItem,
} from "@/lib/business-profiles-client";
import { uploadMedia, mediaSizeError } from "@/lib/media-client";

interface SearchHitLite {
  listingId: string;
  title: string;
  price?: { amount: string; currency: string } | null;
  slug?: string | null;
}

export const Route = createFileRoute("/dashboard/business-profile")({
  beforeLoad: requireAuth,
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

function TextListField({
  icon: Icon,
  label,
  placeholder,
  values,
  onChange,
}: {
  icon: typeof Phone;
  label: string;
  placeholder: string;
  values: string[];
  onChange: (next: string[]) => void;
}) {
  return (
    <div>
      <div className="flex items-center justify-between">
        <label className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <Icon className="size-3.5" /> {label}
        </label>
        <button
          type="button"
          onClick={() => onChange([...values, ""])}
          className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline"
        >
          <Plus className="size-3.5" /> Qo'shish
        </button>
      </div>
      <div className="mt-1.5 space-y-2">
        {values.length === 0 && (
          <p className="text-xs text-muted-foreground/70">Hali qo'shilmagan.</p>
        )}
        {values.map((value, i) => (
          <div key={i} className="flex items-center gap-2">
            <input
              value={value}
              onChange={(e) => onChange(values.map((v, idx) => (idx === i ? e.target.value : v)))}
              placeholder={placeholder}
              className="flex-1 rounded-xl border border-border bg-background px-3 py-2 text-sm outline-none transition focus:ring-2 focus:ring-primary/30"
            />
            <button
              type="button"
              onClick={() => onChange(values.filter((_, idx) => idx !== i))}
              className="rounded-lg p-2 text-muted-foreground transition hover:bg-destructive/10 hover:text-destructive"
            >
              <X className="size-3.5" />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

function PortfolioGallery({ profile }: { profile: BusinessProfile }) {
  const queryClient = useQueryClient();
  const [items, setItems] = useState<PortfolioItem[]>(profile.portfolio ?? []);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    businessProfilesApi
      .listPortfolio(profile.id)
      .then(setItems)
      .catch(() => {});
  }, [profile.id]);

  const refresh = async () => {
    const fresh = await businessProfilesApi.listPortfolio(profile.id);
    setItems(fresh);
    queryClient.invalidateQueries({ queryKey: ["business-profiles"] });
  };

  const handleFile = async (file: File | undefined) => {
    if (!file) return;
    const sizeError = mediaSizeError(file);
    if (sizeError) {
      setError(sizeError);
      return;
    }
    setError(null);
    setUploading(true);
    try {
      const uploaded = await uploadMedia(file, "PROFILE_PORTFOLIO");
      await businessProfilesApi.addPortfolioItem(profile.id, {
        mediaAssetId: uploaded.mediaAssetId,
      });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Fayl yuklab bo'lmadi.");
    } finally {
      setUploading(false);
    }
  };

  const remove = async (itemId: string) => {
    setItems((prev) => prev.filter((i) => i.id !== itemId));
    try {
      await businessProfilesApi.removePortfolioItem(profile.id, itemId);
    } finally {
      refresh();
    }
  };

  return (
    <SectionCard
      title="Portfolio galereyasi"
      icon={ImagePlus}
      description="Rasm (JPEG/PNG/WEBP, maks. 1.2 MB) yoki video (MP4/WEBM, maks. 30 MB) qo'shing."
      index={2}
      action={
        <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-full bg-primary px-3.5 py-1.5 text-xs font-semibold text-primary-foreground transition hover:shadow-glow">
          {uploading ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <Plus className="size-3.5" />
          )}
          Fayl qo'shish
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp,video/mp4,video/webm"
            className="hidden"
            disabled={uploading}
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              handleFile(file);
            }}
          />
        </label>
      }
    >
      {error && (
        <p className="mb-3 rounded-xl bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {error}
        </p>
      )}
      {items.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted-foreground">
          Hali portfolio elementi yo'q.
        </p>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {items.map((item) => (
            <PortfolioTile key={item.id} item={item} onRemove={() => remove(item.id)} />
          ))}
        </div>
      )}
    </SectionCard>
  );
}

function PortfolioTile({ item, onRemove }: { item: PortfolioItem; onRemove: () => void }) {
  const [asset, setAsset] = useState<{ url: string | null; contentType: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    http
      .get<{ url: string | null; contentType: string }>(`/media/${item.mediaAssetId}`)
      .then((a) => {
        if (!cancelled) setAsset(a);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [item.mediaAssetId]);

  const video = asset?.contentType?.startsWith("video/");

  return (
    <div className="group relative aspect-square overflow-hidden rounded-2xl border border-border bg-muted">
      {!asset?.url ? (
        <div className="flex size-full items-center justify-center">
          <Loader2 className="size-5 animate-spin text-muted-foreground" />
        </div>
      ) : video ? (
        <video src={asset.url} preload="metadata" className="size-full object-cover" muted />
      ) : (
        <img src={asset.url} alt="" className="size-full object-cover" />
      )}
      {video && (
        <div className="absolute bottom-2 left-2 inline-flex items-center gap-1 rounded-full bg-black/60 px-2 py-0.5 text-[10px] font-medium text-white">
          <Film className="size-3" /> Video
        </div>
      )}
      <button
        type="button"
        onClick={onRemove}
        className="absolute right-2 top-2 flex size-7 items-center justify-center rounded-full bg-black/60 text-white opacity-0 transition group-hover:opacity-100 hover:bg-destructive"
      >
        <Trash2 className="size-3.5" />
      </button>
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

function BrandingTile({
  label,
  mediaAssetId,
  uploading,
  onUpload,
  onRemove,
}: {
  label: string;
  mediaAssetId?: string | null;
  uploading: boolean;
  onUpload: (file: File | undefined) => void;
  onRemove: () => void;
}) {
  const [asset, setAsset] = useState<{ url: string | null } | null>(null);

  useEffect(() => {
    if (!mediaAssetId) {
      setAsset(null);
      return;
    }
    let cancelled = false;
    http
      .get<{ url: string | null }>(`/media/${mediaAssetId}`)
      .then((a) => {
        if (!cancelled) setAsset(a);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [mediaAssetId]);

  return (
    <div>
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <div className="mt-1.5 flex items-center gap-3">
        <div className="flex h-20 w-32 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-dashed border-border bg-muted">
          {uploading ? (
            <Loader2 className="size-5 animate-spin text-muted-foreground" />
          ) : asset?.url ? (
            <img src={asset.url} alt="" className="size-full object-cover" />
          ) : (
            <ImageIcon className="size-5 text-muted-foreground" />
          )}
        </div>
        <div className="flex flex-col gap-1.5">
          <label className="inline-flex w-fit cursor-pointer items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs font-medium text-foreground transition hover:bg-muted">
            Rasm tanlash
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp"
              className="hidden"
              disabled={uploading}
              onChange={(e) => {
                const file = e.target.files?.[0];
                e.target.value = "";
                onUpload(file);
              }}
            />
          </label>
          {mediaAssetId && (
            <button
              type="button"
              onClick={onRemove}
              className="text-left text-xs text-muted-foreground hover:text-destructive"
            >
              O'chirish
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function BrandingSection({ profile }: { profile: BusinessProfile }) {
  const queryClient = useQueryClient();
  const [uploadingField, setUploadingField] = useState<"logo" | "banner" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const set = async (field: "logo" | "banner", mediaAssetId: string | null) => {
    try {
      await businessProfilesApi.updateBranding(profile.id, {
        logoMediaAssetId: field === "logo" ? mediaAssetId : profile.logoMediaAssetId,
        bannerMediaAssetId: field === "banner" ? mediaAssetId : profile.bannerMediaAssetId,
      });
      await queryClient.invalidateQueries({ queryKey: ["business-profiles"] });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Saqlab bo'lmadi.");
    }
  };

  const handleUpload = async (field: "logo" | "banner", file: File | undefined) => {
    if (!file) return;
    const sizeError = mediaSizeError(file);
    if (sizeError) {
      setError(sizeError);
      return;
    }
    setError(null);
    setUploadingField(field);
    try {
      const uploaded = await uploadMedia(file, "PROFILE_PORTFOLIO");
      await set(field, uploaded.mediaAssetId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Fayl yuklab bo'lmadi.");
    } finally {
      setUploadingField(null);
    }
  };

  return (
    <SectionCard
      title="Logotip va muqova rasmi"
      icon={ImageIcon}
      description="Landing page sarlavhasida shu rasmlar ko'rsatiladi."
      index={1}
    >
      {error && (
        <p className="mb-3 rounded-xl bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {error}
        </p>
      )}
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
        <BrandingTile
          label="Logotip"
          mediaAssetId={profile.logoMediaAssetId}
          uploading={uploadingField === "logo"}
          onUpload={(f) => handleUpload("logo", f)}
          onRemove={() => set("logo", null)}
        />
        <BrandingTile
          label="Muqova rasmi (banner)"
          mediaAssetId={profile.bannerMediaAssetId}
          uploading={uploadingField === "banner"}
          onUpload={(f) => handleUpload("banner", f)}
          onRemove={() => set("banner", null)}
        />
      </div>
    </SectionCard>
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
