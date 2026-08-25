import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  ShieldAlert,
  Loader2,
  Building2,
  CheckCircle2,
  XCircle,
  Clock3,
  FileImage,
  ImageUp,
  Palette,
} from "lucide-react";
import { requireAdmin } from "@/lib/require-auth";
import { DashboardShell } from "@/components/layout/DashboardShell";
import { SectionCard } from "@/components/dashboard/SectionCard";
import { EmptyState } from "@/components/dashboard/EmptyState";
import { StatCard } from "@/components/dashboard/StatCard";
import {
  adminBusinessProfilesApi,
  adminVerificationApi,
  businessProfilesApi,
  MAIN_CATEGORIES,
  MAIN_CATEGORY_ACCENT,
  MAIN_CATEGORY_IMAGE,
  MAIN_CATEGORY_LABEL,
  type BusinessProfile,
  type MainCategory,
  type VerificationCase,
} from "@/lib/business-profiles-client";
import {
  getB2bSectorIcons,
  updateB2bSectorIcons,
  uploadCategoryIcon,
  type B2bSectorIcons,
} from "@/lib/owner-admin-client";
import { getMediaAssetUrl } from "@/lib/media-client";
import { ApiError } from "@/lib/http";
import { useMe } from "@/features/auth/useAuth";

export const Route = createFileRoute("/admin/organizations")({
  beforeLoad: requireAdmin,
  ssr: false,
  head: () => ({ meta: [{ title: "Tashkilotlar (B2B) — ActiveHome Admin" }] }),
  component: Page,
});

const CASE_STATUS_LABEL: Record<VerificationCase["status"], string> = {
  REQUESTED: "So'ralgan",
  IN_REVIEW: "Ko'rib chiqilmoqda",
  APPROVED: "Tasdiqlangan",
  REJECTED: "Rad etilgan",
};

const CASE_STATUS_CLASS: Record<VerificationCase["status"], string> = {
  REQUESTED: "bg-amber-500/10 text-amber-600",
  IN_REVIEW: "bg-primary/10 text-primary",
  APPROVED: "bg-success/10 text-success",
  REJECTED: "bg-destructive/10 text-destructive",
};

function companyName(profile: { name: BusinessProfile["name"]; id: string }): string {
  return (
    profile.name.uz_latn || profile.name.uz_cyrl || profile.name.ru || profile.name.en || profile.id
  );
}

// --- "Yangi arizalar" (ADR-0012 registration-approval gate) ----------------------------------

function RegistrationRow({ profile, index }: { profile: BusinessProfile; index: number }) {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState<"APPROVED" | "REJECTED" | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const decide = async (outcome: "APPROVED" | "REJECTED") => {
    setBusy(outcome);
    setError(null);
    try {
      await adminBusinessProfilesApi.decide(profile.id, {
        outcome,
        reason: reason.trim() || undefined,
      });
      await queryClient.invalidateQueries({ queryKey: ["admin", "business-profiles"] });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Qarorni saqlab bo'lmadi.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: Math.min(index, 6) * 0.04, duration: 0.35 }}
      className="rounded-2xl border border-border/70 bg-background/50 p-5 transition hover:border-primary/30 hover:bg-background"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-foreground">{companyName(profile)}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {profile.mainCategory
              ? MAIN_CATEGORY_LABEL[profile.mainCategory]
              : "Sektor tanlanmagan"}
            {profile.createdAt
              ? ` — ${new Date(profile.createdAt).toLocaleDateString("uz-UZ")}`
              : ""}
          </p>
          {profile.address && (
            <p className="mt-0.5 text-xs text-muted-foreground">{profile.address}</p>
          )}
        </div>
      </div>

      <div className="mt-4 space-y-3 border-t border-border/60 pt-4">
        <input
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Izoh (ixtiyoriy) — rad etishda ko'rsatish tavsiya etiladi"
          className="w-full rounded-lg border border-border bg-background px-3 py-2 text-xs outline-none focus:border-primary"
        />
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => decide("APPROVED")}
            className="inline-flex items-center gap-1.5 rounded-full bg-success/10 px-3 py-1.5 text-xs font-semibold text-success transition hover:bg-success/20 disabled:opacity-50"
          >
            {busy === "APPROVED" ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <CheckCircle2 className="size-3.5" />
            )}
            Tasdiqlash
          </button>
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => decide("REJECTED")}
            className="inline-flex items-center gap-1.5 rounded-full bg-destructive/10 px-3 py-1.5 text-xs font-semibold text-destructive transition hover:bg-destructive/20 disabled:opacity-50"
          >
            {busy === "REJECTED" ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <XCircle className="size-3.5" />
            )}
            Rad etish
          </button>
        </div>
      </div>
      {error && <p className="mt-2 text-xs text-destructive">{error}</p>}
    </motion.div>
  );
}

function RegistrationsPanel() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["admin", "business-profiles", "PENDING_REVIEW"],
    queryFn: () => adminBusinessProfilesApi.list({ status: "PENDING_REVIEW", limit: 50 }),
    retry: false,
  });
  const items = data?.items ?? [];

  return (
    <>
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <StatCard
          icon={Clock3}
          label="Ko'rib chiqilishi kerak"
          value={items.length}
          accent="warning"
          index={0}
        />
        <StatCard
          icon={Building2}
          label="Sahifada"
          value={items.length}
          accent="primary"
          index={1}
        />
      </section>

      <SectionCard title="Yangi arizalar" icon={Building2} index={0}>
        {isLoading && (
          <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Yuklanmoqda…
          </div>
        )}
        {error instanceof ApiError && error.status === 403 && (
          <div className="flex items-start gap-3 rounded-2xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
            <ShieldAlert className="mt-0.5 size-5 shrink-0" />
            Bu bo'lim faqat kompaniyalarni boshqarish huquqiga ega adminlar uchun.
          </div>
        )}
        {data && items.length === 0 && (
          <EmptyState
            icon={CheckCircle2}
            title="Yangi ariza yo'q"
            description="Ko'rib chiqilishi kerak bo'lgan yangi tashkilot arizalari hozircha mavjud emas."
          />
        )}
      </SectionCard>

      <div className="space-y-4">
        {items.map((item, i) => (
          <RegistrationRow key={item.id} profile={item} index={i} />
        ))}
      </div>
    </>
  );
}

// --- "Verifikatsiya so'rovlari" (pre-existing trust-badge review queue) ----------------------

function DocumentThumb({ mediaAssetId }: { mediaAssetId: string }) {
  const { data: url } = useQuery({
    queryKey: ["media-asset-url", mediaAssetId],
    queryFn: () => getMediaAssetUrl(mediaAssetId),
  });
  if (!url) {
    return (
      <div className="flex size-16 items-center justify-center rounded-lg border border-dashed border-border bg-muted">
        <FileImage className="size-5 text-muted-foreground" />
      </div>
    );
  }
  return (
    <a href={url} target="_blank" rel="noreferrer" className="block size-16 shrink-0">
      <img
        src={url}
        alt="Hujjat"
        className="size-16 rounded-lg border border-border object-cover"
      />
    </a>
  );
}

function CaseRow({ item, index }: { item: VerificationCase; index: number }) {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState<"APPROVED" | "REJECTED" | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: profile } = useQuery({
    queryKey: ["business-profiles", item.businessProfileId],
    queryFn: () => businessProfilesApi.get(item.businessProfileId),
  });

  const pending = item.status === "REQUESTED" || item.status === "IN_REVIEW";

  const decide = async (outcome: "APPROVED" | "REJECTED") => {
    setBusy(outcome);
    setError(null);
    try {
      await adminVerificationApi.decide(item.id, { outcome, reason: reason.trim() || undefined });
      await queryClient.invalidateQueries({ queryKey: ["admin", "verification-queue"] });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Qarorni saqlab bo'lmadi.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: Math.min(index, 6) * 0.04, duration: 0.35 }}
      className="rounded-2xl border border-border/70 bg-background/50 p-5 transition hover:border-primary/30 hover:bg-background"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${CASE_STATUS_CLASS[item.status]}`}
            >
              {CASE_STATUS_LABEL[item.status]}
            </span>
            {item.slaDueAt && (
              <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                <Clock3 className="size-3" /> Muddat: {new Date(item.slaDueAt).toLocaleDateString()}
              </span>
            )}
          </div>
          <p className="mt-1.5 text-sm font-semibold text-foreground">
            {profile ? companyName(profile) : item.businessProfileId}
          </p>
          {item.decision && (
            <p className="mt-1 text-xs font-medium text-muted-foreground">
              Oldingi qaror: {CASE_STATUS_LABEL[item.decision.outcome ?? "REQUESTED"]}
              {item.decision.reason ? ` — ${item.decision.reason}` : ""}
            </p>
          )}
        </div>
      </div>

      {item.documents && item.documents.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {item.documents.map((doc, i) => (
            <DocumentThumb key={doc.id ?? i} mediaAssetId={doc.mediaAssetId} />
          ))}
        </div>
      )}

      {pending && (
        <div className="mt-4 space-y-3 border-t border-border/60 pt-4">
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Izoh (ixtiyoriy) — rad etishda ko'rsatish tavsiya etiladi"
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-xs outline-none focus:border-primary"
          />
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => decide("APPROVED")}
              className="inline-flex items-center gap-1.5 rounded-full bg-success/10 px-3 py-1.5 text-xs font-semibold text-success transition hover:bg-success/20 disabled:opacity-50"
            >
              {busy === "APPROVED" ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <CheckCircle2 className="size-3.5" />
              )}
              Tasdiqlash
            </button>
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => decide("REJECTED")}
              className="inline-flex items-center gap-1.5 rounded-full bg-destructive/10 px-3 py-1.5 text-xs font-semibold text-destructive transition hover:bg-destructive/20 disabled:opacity-50"
            >
              {busy === "REJECTED" ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <XCircle className="size-3.5" />
              )}
              Rad etish
            </button>
          </div>
        </div>
      )}
      {error && <p className="mt-2 text-xs text-destructive">{error}</p>}
    </motion.div>
  );
}

function VerificationPanel() {
  const [statusFilter, setStatusFilter] = useState<VerificationCase["status"] | "">("REQUESTED");

  const { data, isLoading, error } = useQuery({
    queryKey: ["admin", "verification-queue", statusFilter],
    queryFn: () => adminVerificationApi.listQueue({ status: statusFilter || undefined, limit: 50 }),
    retry: false,
  });

  const items = data?.items ?? [];

  return (
    <>
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard
          icon={Building2}
          label="Ko'rsatilmoqda"
          value={items.length}
          accent="primary"
          index={0}
        />
        <StatCard
          icon={Clock3}
          label="Kutilmoqda"
          value={items.filter((i) => i.status === "REQUESTED" || i.status === "IN_REVIEW").length}
          accent="warning"
          index={1}
        />
        <StatCard
          icon={CheckCircle2}
          label="Tasdiqlangan (shu sahifada)"
          value={items.filter((i) => i.status === "APPROVED").length}
          accent="success"
          index={2}
        />
      </section>

      <SectionCard
        title="Filtr"
        icon={Clock3}
        index={0}
        action={
          <div className="flex flex-wrap items-center gap-2">
            {(["REQUESTED", "IN_REVIEW", "APPROVED", "REJECTED", ""] as const).map((s) => (
              <button
                key={s || "all"}
                type="button"
                onClick={() => setStatusFilter(s)}
                className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${
                  statusFilter === s
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-muted-foreground hover:bg-primary/10 hover:text-primary"
                }`}
              >
                {s === "" ? "Barchasi" : CASE_STATUS_LABEL[s]}
              </button>
            ))}
          </div>
        }
      >
        {isLoading && (
          <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Yuklanmoqda…
          </div>
        )}

        {error instanceof ApiError && error.status === 403 && (
          <div className="flex items-start gap-3 rounded-2xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
            <ShieldAlert className="mt-0.5 size-5 shrink-0" />
            Bu sahifa faqat tasdiqlash (reviewer) huquqiga ega adminlar uchun.
          </div>
        )}

        {data && items.length === 0 && (
          <EmptyState
            icon={Building2}
            title="So'rov topilmadi"
            description="Tanlangan filtrga mos ishonch nishoni so'rovi yo'q."
          />
        )}
      </SectionCard>

      <div className="space-y-4">
        {items.map((item, i) => (
          <CaseRow key={item.id} item={item} index={i} />
        ))}
      </div>
    </>
  );
}

// --- "Sektor ikonkalari" (ADR-0012 admin-editable B2B sector icons) --------------------------

function SectorIconRow({
  category,
  override,
  onChange,
}: {
  category: MainCategory;
  override: { iconUrl?: string; accentColor?: string };
  onChange: (next: { iconUrl?: string; accentColor?: string }) => void;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const previewUrl = override.iconUrl || MAIN_CATEGORY_IMAGE[category];
  const accent = override.accentColor || MAIN_CATEGORY_ACCENT[category];

  const handleFile = async (file: File) => {
    setUploading(true);
    setError(null);
    try {
      const { url } = await uploadCategoryIcon(file);
      onChange({ ...override, iconUrl: url ?? override.iconUrl });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Yuklab bo'lmadi.");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-4 rounded-2xl border border-border/70 bg-background/50 p-4">
      <img
        src={previewUrl}
        alt={MAIN_CATEGORY_LABEL[category]}
        className="size-14 shrink-0 rounded-xl border border-border object-cover"
      />
      <div className="min-w-[10rem] flex-1">
        <p className="text-sm font-semibold text-foreground">{MAIN_CATEGORY_LABEL[category]}</p>
        <p className="text-xs text-muted-foreground">
          {override.iconUrl ? "Maxsus ikonka o'rnatilgan" : "Standart rasm ishlatilmoqda"}
        </p>
      </div>
      <div className="flex items-center gap-2">
        <input
          type="color"
          value={accent}
          onChange={(e) => onChange({ ...override, accentColor: e.target.value })}
          className="size-9 cursor-pointer rounded-lg border border-border bg-transparent p-0.5"
          title="Aksent rang"
        />
        <input
          ref={fileInput}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void handleFile(file);
            e.target.value = "";
          }}
        />
        <button
          type="button"
          disabled={uploading}
          onClick={() => fileInput.current?.click()}
          className="inline-flex items-center gap-1.5 rounded-full bg-muted px-3 py-1.5 text-xs font-semibold text-foreground transition hover:bg-primary/10 hover:text-primary disabled:opacity-50"
        >
          {uploading ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <ImageUp className="size-3.5" />
          )}
          Rasm yuklash
        </button>
      </div>
      {error && <p className="w-full text-xs text-destructive">{error}</p>}
    </div>
  );
}

function SectorIconsPanel() {
  const queryClient = useQueryClient();
  const { data: saved, isLoading } = useQuery({
    queryKey: ["admin", "b2b-sector-icons"],
    queryFn: getB2bSectorIcons,
  });
  const [draft, setDraft] = useState<B2bSectorIcons | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedOk, setSavedOk] = useState(false);

  const icons = draft ?? saved ?? {};

  const setOverride = (
    category: MainCategory,
    next: { iconUrl?: string; accentColor?: string },
  ) => {
    setDraft({ ...icons, [category]: next });
    setSavedOk(false);
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await updateB2bSectorIcons(icons);
      await queryClient.invalidateQueries({ queryKey: ["admin", "b2b-sector-icons"] });
      setDraft(null);
      setSavedOk(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Saqlab bo'lmadi.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <SectionCard
      title="Sektor ikonkalari"
      icon={Palette}
      index={0}
      action={
        <button
          type="button"
          disabled={saving || draft === null}
          onClick={save}
          className="inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-1.5 text-xs font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
        >
          {saving && <Loader2 className="size-3.5 animate-spin" />}
          Saqlash
        </button>
      }
    >
      <p className="mb-4 text-sm text-muted-foreground">
        Har bir B2B sektor uchun rasm va aksent rangni o'zgartiring — o'rnatilmagan sektorlar
        standart rasmni ko'rsatadi.
      </p>
      {isLoading && (
        <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Yuklanmoqda…
        </div>
      )}
      {!isLoading && (
        <div className="space-y-3">
          {MAIN_CATEGORIES.map((category) => (
            <SectorIconRow
              key={category}
              category={category}
              override={icons[category] ?? {}}
              onChange={(next) => setOverride(category, next)}
            />
          ))}
        </div>
      )}
      {savedOk && <p className="mt-3 text-xs font-medium text-success">Saqlandi.</p>}
      {error && <p className="mt-3 text-xs text-destructive">{error}</p>}
    </SectionCard>
  );
}

// --- page ---------------------------------------------------------------------------------

type Mode = "registrations" | "verification" | "icons";

function Page() {
  const { data: account } = useMe();
  const [mode, setMode] = useState<Mode>("registrations");

  return (
    <DashboardShell account={account}>
      <div className="mx-auto max-w-5xl space-y-8 px-4 py-8 lg:px-8">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          className="relative overflow-hidden rounded-3xl border border-border bg-card p-8 shadow-soft"
        >
          <div className="gradient-mesh absolute inset-0 -z-10 opacity-70" />
          <h1 className="font-display text-3xl font-semibold tracking-tight">Tashkilotlar (B2B)</h1>
          <p className="mt-2 max-w-xl text-sm text-muted-foreground">
            Yangi tashkilot arizalarini ko'rib chiqing, ishonch nishoni so'rovlarini boshqaring va
            B2B sektor ikonkalarini sozlang.
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            {(
              [
                ["registrations", "Yangi arizalar"],
                ["verification", "Verifikatsiya so'rovlari"],
                ["icons", "Sektor ikonkalari"],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => setMode(value)}
                className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                  mode === value
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-muted-foreground hover:bg-primary/10 hover:text-primary"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </motion.div>

        {mode === "registrations" && <RegistrationsPanel />}
        {mode === "verification" && <VerificationPanel />}
        {mode === "icons" && <SectorIconsPanel />}
      </div>
    </DashboardShell>
  );
}
