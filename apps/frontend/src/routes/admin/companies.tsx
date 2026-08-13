import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { motion } from "framer-motion";
import { ShieldAlert, Loader2, Building2, Trash2, CheckCircle2 } from "lucide-react";
import { requireAdmin } from "@/lib/require-auth";
import { DashboardShell } from "@/components/layout/DashboardShell";
import { SectionCard } from "@/components/dashboard/SectionCard";
import { EmptyState } from "@/components/dashboard/EmptyState";
import { StatCard } from "@/components/dashboard/StatCard";
import {
  adminBusinessProfilesApi,
  PROFILE_TYPE_LABEL,
  type BusinessProfile,
} from "@/lib/business-profiles-client";
import { ApiError } from "@/lib/http";
import { useMe } from "@/features/auth/useAuth";

export const Route = createFileRoute("/admin/companies")({
  beforeLoad: requireAdmin,
  ssr: false,
  head: () => ({ meta: [{ title: "Kompaniyalar — ActiveHome Admin" }] }),
  component: Page,
});

const STATUS_LABEL: Record<BusinessProfile["status"], string> = {
  CREATED: "Yaratilgan",
  ACTIVE: "Faol",
  ARCHIVED: "O'chirilgan",
};

const STATUS_CLASS: Record<BusinessProfile["status"], string> = {
  CREATED: "bg-muted text-muted-foreground",
  ACTIVE: "bg-success/10 text-success",
  ARCHIVED: "bg-destructive/10 text-destructive",
};

function companyName(profile: BusinessProfile): string {
  return (
    profile.name.uz_latn || profile.name.uz_cyrl || profile.name.ru || profile.name.en || profile.id
  );
}

function CompanyRow({ profile, index }: { profile: BusinessProfile; index: number }) {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin", "companies"] });

  const deletePermanently = async () => {
    if (
      !window.confirm(
        `"${companyName(profile)}" kompaniyasini BUTUNLAY o'chirmoqchimisiz? Bu amalni qaytarib bo'lmaydi — kompaniya barcha ommaviy ro'yxatlardan yo'qoladi.`,
      )
    ) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await adminBusinessProfilesApi.archive(profile.id);
      await invalidate();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "O'chirib bo'lmadi.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: Math.min(index, 8) * 0.03, duration: 0.3 }}
      className="rounded-2xl border border-border/70 bg-background/50 p-4 transition hover:border-primary/30 hover:bg-background"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${STATUS_CLASS[profile.status]}`}
            >
              {STATUS_LABEL[profile.status]}
            </span>
            <span className="text-xs text-muted-foreground">
              {PROFILE_TYPE_LABEL[profile.profileType]}
            </span>
            {profile.createdAt && (
              <span className="text-xs text-muted-foreground">
                {new Date(profile.createdAt).toLocaleDateString()}
              </span>
            )}
          </div>
          <div className="mt-1 truncate text-sm font-semibold text-foreground">
            {companyName(profile)}
          </div>
          <div className="truncate text-xs text-muted-foreground">{profile.id}</div>
        </div>
        <div className="flex flex-wrap items-center gap-2 sm:shrink-0">
          {profile.status === "ARCHIVED" ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-muted px-3 py-1.5 text-xs font-semibold text-muted-foreground">
              <CheckCircle2 className="size-3.5" /> O'chirilgan
            </span>
          ) : (
            <button
              type="button"
              disabled={busy}
              onClick={deletePermanently}
              title="Butunlay o'chirish — qaytarib bo'lmaydi"
              className="inline-flex items-center gap-1.5 rounded-full bg-destructive px-3 py-1.5 text-xs font-semibold text-destructive-foreground transition hover:opacity-90 disabled:opacity-50"
            >
              {busy ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <Trash2 className="size-3.5" />
              )}
              O'chirish
            </button>
          )}
        </div>
      </div>
      {error && <p className="mt-2 text-xs text-destructive">{error}</p>}
    </motion.div>
  );
}

function Page() {
  const { data: account } = useMe();
  const [statusFilter, setStatusFilter] = useState<BusinessProfile["status"] | "">("");

  const { data, isLoading, error } = useQuery({
    queryKey: ["admin", "companies", statusFilter],
    queryFn: () => adminBusinessProfilesApi.list({ status: statusFilter || undefined, limit: 50 }),
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
          <h1 className="font-display text-3xl font-semibold tracking-tight">Kompaniyalar</h1>
          <p className="mt-2 max-w-xl text-sm text-muted-foreground">
            Platformadagi barcha ro'yxatdan o'tgan kompaniyalar (yuridik shaxs profillari).
          </p>
        </motion.div>

        <section className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <StatCard
            icon={Building2}
            label="Jami kompaniyalar"
            value={data?.page.total ?? items.length}
            accent="primary"
            index={0}
          />
          <StatCard
            icon={CheckCircle2}
            label="Faol (shu sahifada)"
            value={items.filter((i) => i.status === "ACTIVE").length}
            accent="success"
            index={1}
          />
          <StatCard
            icon={Trash2}
            label="O'chirilgan (shu sahifada)"
            value={items.filter((i) => i.status === "ARCHIVED").length}
            accent="warning"
            index={2}
          />
        </section>

        <SectionCard
          title="Kompaniyalar ro'yxati"
          icon={Building2}
          index={0}
          action={
            <div className="flex flex-wrap items-center gap-2">
              {(["", "ACTIVE", "ARCHIVED"] as const).map((s) => (
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
              Bu sahifa faqat "profiles:profile:manage" ruxsatiga ega adminlar uchun.
            </div>
          )}

          {data && items.length === 0 && (
            <EmptyState
              icon={Building2}
              title="Kompaniya topilmadi"
              description="Filtrni o'zgartirib ko'ring."
            />
          )}

          <div className="space-y-3">
            {items.map((profile, i) => (
              <CompanyRow key={profile.id} profile={profile} index={i} />
            ))}
          </div>
        </SectionCard>
      </div>
    </DashboardShell>
  );
}
