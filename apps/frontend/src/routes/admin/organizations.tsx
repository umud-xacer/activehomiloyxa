import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { motion } from "framer-motion";
import {
  ShieldAlert,
  Loader2,
  Building2,
  CheckCircle2,
  XCircle,
  Clock3,
  FileImage,
} from "lucide-react";
import { requireAdmin } from "@/lib/require-auth";
import { DashboardShell } from "@/components/layout/DashboardShell";
import { SectionCard } from "@/components/dashboard/SectionCard";
import { EmptyState } from "@/components/dashboard/EmptyState";
import { StatCard } from "@/components/dashboard/StatCard";
import {
  adminVerificationApi,
  businessProfilesApi,
  type VerificationCase,
} from "@/lib/business-profiles-client";
import { getMediaAssetUrl } from "@/lib/media-client";
import { ApiError } from "@/lib/http";
import { useMe } from "@/features/auth/useAuth";

export const Route = createFileRoute("/admin/organizations")({
  beforeLoad: requireAdmin,
  ssr: false,
  head: () => ({ meta: [{ title: "Tashkilotlar (B2B) — ActiveHome Admin" }] }),
  component: Page,
});

const STATUS_LABEL: Record<VerificationCase["status"], string> = {
  REQUESTED: "So'ralgan",
  IN_REVIEW: "Ko'rib chiqilmoqda",
  APPROVED: "Tasdiqlangan",
  REJECTED: "Rad etilgan",
};

const STATUS_CLASS: Record<VerificationCase["status"], string> = {
  REQUESTED: "bg-amber-500/10 text-amber-600",
  IN_REVIEW: "bg-primary/10 text-primary",
  APPROVED: "bg-success/10 text-success",
  REJECTED: "bg-destructive/10 text-destructive",
};

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
              className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${STATUS_CLASS[item.status]}`}
            >
              {STATUS_LABEL[item.status]}
            </span>
            {item.slaDueAt && (
              <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                <Clock3 className="size-3" /> Muddat: {new Date(item.slaDueAt).toLocaleDateString()}
              </span>
            )}
          </div>
          <p className="mt-1.5 text-sm font-semibold text-foreground">
            {profile
              ? profile.name.uz_latn || profile.name.ru || profile.name.en || profile.id
              : item.businessProfileId}
          </p>
          {item.decision && (
            <p className="mt-1 text-xs font-medium text-muted-foreground">
              Oldingi qaror: {STATUS_LABEL[item.decision.outcome ?? "REQUESTED"]}
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

function Page() {
  const { data: account } = useMe();
  const [statusFilter, setStatusFilter] = useState<VerificationCase["status"] | "">("REQUESTED");

  const { data, isLoading, error } = useQuery({
    queryKey: ["admin", "verification-queue", statusFilter],
    queryFn: () => adminVerificationApi.listQueue({ status: statusFilter || undefined, limit: 50 }),
    retry: false,
  });

  const items = data?.items ?? [];

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
          <h1 className="font-display text-3xl font-semibold tracking-tight">
            Tashkilotlar (B2B) — ishonch nishoni so'rovlari
          </h1>
          <p className="mt-2 max-w-xl text-sm text-muted-foreground">
            Kompaniyalarning yuborgan hujjatlarini ko'rib chiqing va ishonch nishonini (verified
            badge) tasdiqlang yoki rad eting.
          </p>
        </motion.div>

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
                  {s === "" ? "Barchasi" : STATUS_LABEL[s]}
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
      </div>
    </DashboardShell>
  );
}
