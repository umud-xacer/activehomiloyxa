import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { motion } from "framer-motion";
import {
  ShieldAlert,
  Check,
  X,
  Loader2,
  Inbox,
  Users,
  Building2,
  TrendingUp,
  ClipboardList,
} from "lucide-react";
import { requireAdmin } from "@/lib/require-auth";
import { DashboardShell } from "@/components/layout/DashboardShell";
import { StatCard } from "@/components/dashboard/StatCard";
import { SectionCard } from "@/components/dashboard/SectionCard";
import { EmptyState } from "@/components/dashboard/EmptyState";
import { registrationReviewApi, type RegistrationQueueItem } from "@/lib/auth-client";
import { ApiError } from "@/lib/http";
import { useMe } from "@/features/auth/useAuth";

export const Route = createFileRoute("/admin/registrations")({
  beforeLoad: requireAdmin,
  // See /admin's own Route options for why: `requireAdmin` only enforces client-side.
  ssr: false,
  head: () => ({
    meta: [{ title: "Ro'yxatdan o'tishlarni ko'rib chiqish — ActiveHome Admin" }],
  }),
  component: Page,
});

const ROLE_LABEL: Record<string, string> = {
  INDIVIDUAL: "Jismoniy shaxs",
  LEGAL_ENTITY: "Yuridik shaxs",
  INVESTOR: "Investor",
};

function AnketaTable({ anketa }: { anketa: Record<string, unknown> }) {
  const entries = Object.entries(anketa);
  if (entries.length === 0) return null;
  return (
    <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-1.5 text-xs sm:grid-cols-2">
      {entries.map(([key, value]) => (
        <div key={key} className="flex justify-between gap-2 border-b border-border/60 py-1">
          <dt className="capitalize text-muted-foreground">{key}</dt>
          <dd className="truncate text-right font-medium text-foreground">{String(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

function QueueRow({ item, index }: { item: RegistrationQueueItem; index: number }) {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const decide = async (outcome: "APPROVED" | "REJECTED") => {
    setError(null);
    setBusy(outcome === "APPROVED" ? "approve" : "reject");
    try {
      await registrationReviewApi.decide(
        item.id,
        outcome,
        outcome === "REJECTED" ? "Anketa admin tomonidan rad etildi" : undefined,
      );
      await queryClient.invalidateQueries({ queryKey: ["admin", "registration-queue"] });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Amalni bajarib bo'lmadi.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, x: -12 }}
      transition={{ delay: Math.min(index, 6) * 0.04, duration: 0.35 }}
      className="rounded-2xl border border-border/70 bg-background/50 p-5 transition hover:border-primary/30 hover:bg-background"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-primary/10 px-2.5 py-0.5 text-[11px] font-semibold text-primary">
              {ROLE_LABEL[item.accountKind] ?? item.accountKind}
            </span>
            <span className="text-xs text-muted-foreground">
              {new Date(item.createdAt).toLocaleString()}
            </span>
          </div>
          <div className="mt-1.5 text-sm font-semibold text-foreground">
            {item.displayName || "—"}
          </div>
          <div className="text-xs text-muted-foreground">{item.email || item.phoneNumber}</div>
          <AnketaTable anketa={item.anketa} />
        </div>
        <div className="flex shrink-0 gap-2">
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => decide("APPROVED")}
            className="inline-flex items-center gap-1.5 rounded-full bg-success/10 px-3 py-1.5 text-xs font-semibold text-success transition hover:bg-success/20 disabled:opacity-50"
          >
            {busy === "approve" ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Check className="size-3.5" />
            )}
            Tasdiqlash
          </button>
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => decide("REJECTED")}
            className="inline-flex items-center gap-1.5 rounded-full bg-destructive/10 px-3 py-1.5 text-xs font-semibold text-destructive transition hover:bg-destructive/20 disabled:opacity-50"
          >
            {busy === "reject" ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <X className="size-3.5" />
            )}
            Rad etish
          </button>
        </div>
      </div>
      {error && <p className="mt-2 text-xs text-destructive">{error}</p>}
    </motion.div>
  );
}

function Page() {
  const { data: account } = useMe();
  const { data, isLoading, error } = useQuery({
    queryKey: ["admin", "registration-queue"],
    queryFn: () => registrationReviewApi.listQueue(),
    retry: false,
  });

  const items = data?.items ?? [];
  const counts = {
    INDIVIDUAL: items.filter((i) => i.accountKind === "INDIVIDUAL").length,
    LEGAL_ENTITY: items.filter((i) => i.accountKind === "LEGAL_ENTITY").length,
    INVESTOR: items.filter((i) => i.accountKind === "INVESTOR").length,
  };

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
            Ro'yxatdan o'tishlarni ko'rib chiqish
          </h1>
          <p className="mt-2 max-w-xl text-sm text-muted-foreground">
            Yangi akkauntlar anketasini tekshiring, tasdiqlang yoki rad eting (ADR-0007).
          </p>
        </motion.div>

        <section className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <StatCard
            icon={ClipboardList}
            label="Jami kutilmoqda"
            value={items.length}
            accent="primary"
            index={0}
          />
          <StatCard
            icon={Users}
            label="Jismoniy shaxs"
            value={counts.INDIVIDUAL}
            accent="info"
            index={1}
          />
          <StatCard
            icon={Building2}
            label="Yuridik shaxs"
            value={counts.LEGAL_ENTITY}
            accent="success"
            index={2}
          />
          <StatCard
            icon={TrendingUp}
            label="Investor"
            value={counts.INVESTOR}
            accent="warning"
            index={3}
          />
        </section>

        <SectionCard title="Kutilayotgan so'rovlar" icon={ClipboardList} index={0}>
          {isLoading && (
            <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" /> Yuklanmoqda…
            </div>
          )}

          {error instanceof ApiError && error.status === 403 && (
            <div className="flex items-start gap-3 rounded-2xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
              <ShieldAlert className="mt-0.5 size-5 shrink-0" />
              Bu sahifa faqat "identity:registration:review" ruxsatiga ega adminlar uchun.
            </div>
          )}

          {data && items.length === 0 && (
            <EmptyState
              icon={Inbox}
              title="Hozircha so'rov yo'q"
              description="Ko'rib chiqilishi kerak bo'lgan yangi ro'yxatdan o'tish yo'q."
            />
          )}

          <div className="space-y-4">
            {items.map((item, i) => (
              <QueueRow key={item.id} item={item} index={i} />
            ))}
          </div>
        </SectionCard>
      </div>
    </DashboardShell>
  );
}
