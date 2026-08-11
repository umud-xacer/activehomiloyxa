import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { motion } from "framer-motion";
import {
  ShieldAlert,
  Loader2,
  Flag,
  Inbox,
  Home,
  MessageSquare,
  User as UserIcon,
  Building2,
  Bot,
  Megaphone,
} from "lucide-react";
import { requireAdmin } from "@/lib/require-auth";
import { DashboardShell } from "@/components/layout/DashboardShell";
import { SectionCard } from "@/components/dashboard/SectionCard";
import { EmptyState } from "@/components/dashboard/EmptyState";
import { StatCard } from "@/components/dashboard/StatCard";
import {
  moderationApi,
  ACTIONS_BY_SUBJECT_TYPE,
  type ModerationCase,
  type ModerationCaseStatus,
  type ModerationSubjectType,
  type ModerationAction,
} from "@/lib/moderation-client";
import { ApiError } from "@/lib/http";
import { useMe } from "@/features/auth/useAuth";

export const Route = createFileRoute("/admin/moderation")({
  beforeLoad: requireAdmin,
  ssr: false,
  head: () => ({ meta: [{ title: "Moderatsiya — ActiveHome Admin" }] }),
  component: Page,
});

const STATUS_LABEL: Record<ModerationCaseStatus, string> = {
  OPEN: "Ochiq",
  IN_REVIEW: "Ko'rib chiqilmoqda",
  RESOLVED: "Yakunlangan",
};

const STATUS_CLASS: Record<ModerationCaseStatus, string> = {
  OPEN: "bg-destructive/10 text-destructive",
  IN_REVIEW: "bg-amber-500/10 text-amber-600",
  RESOLVED: "bg-success/10 text-success",
};

const SUBJECT_ICON: Record<ModerationSubjectType, typeof Home> = {
  LISTING: Home,
  CONVERSATION: MessageSquare,
  USER: UserIcon,
  PROFILE: Building2,
};

const SUBJECT_LABEL: Record<ModerationSubjectType, string> = {
  LISTING: "E'lon",
  CONVERSATION: "Suhbat",
  USER: "Foydalanuvchi",
  PROFILE: "Kompaniya profili",
};

const ACTION_LABEL: Record<ModerationAction, string> = {
  HIDE: "Yashirish",
  REJECT: "Rad etish",
  SUSPEND: "To'xtatib turish",
  REQUEST_CORRECTION: "Tuzatish so'rash",
  REMOVE: "O'chirish",
  SUSPEND_ACCOUNT: "Akkauntni bloklash",
  DISMISS: "Rad qilish (asossiz)",
  REVOKE_BADGE: "Belgini bekor qilish",
  ARCHIVE_PROFILE: "Profilni arxivlash",
};

const ORIGIN_LABEL: Record<ModerationCase["originType"], string> = {
  USER_REPORT: "Foydalanuvchi shikoyati",
  AUTOMATED_FLAG: "Avtomatik aniqlash",
};

function CaseRow({ item, index }: { item: ModerationCase; index: number }) {
  const queryClient = useQueryClient();
  const [busyAction, setBusyAction] = useState<ModerationAction | null>(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  const Icon = SUBJECT_ICON[item.subjectType];
  const availableActions = ACTIONS_BY_SUBJECT_TYPE[item.subjectType];
  const resolved = item.status === "RESOLVED";

  const apply = async (action: ModerationAction) => {
    setBusyAction(action);
    setError(null);
    try {
      await moderationApi.applyAction(item.id, action, note.trim() || undefined);
      await queryClient.invalidateQueries({ queryKey: ["admin", "moderation-queue"] });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Amalni bajarib bo'lmadi.");
    } finally {
      setBusyAction(null);
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
            <span className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-2.5 py-0.5 text-[11px] font-semibold text-primary">
              <Icon className="size-3" /> {SUBJECT_LABEL[item.subjectType]}
            </span>
            <span
              className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${STATUS_CLASS[item.status]}`}
            >
              {STATUS_LABEL[item.status]}
            </span>
            <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
              {item.originType === "AUTOMATED_FLAG" ? (
                <Bot className="size-3" />
              ) : (
                <Flag className="size-3" />
              )}
              {ORIGIN_LABEL[item.originType]}
            </span>
            <span className="text-xs text-muted-foreground">
              {new Date(item.createdAt).toLocaleString()}
            </span>
          </div>
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="mt-1.5 text-left text-sm font-semibold text-foreground hover:text-primary"
          >
            {item.subjectId}
          </button>
          {(item.reportReason || item.ruleKey) && (
            <p className="mt-1 text-xs text-muted-foreground">
              {item.reportReason ?? `Qoida: ${item.ruleKey}`}
            </p>
          )}
          {item.resolutionAction && (
            <p className="mt-1 text-xs font-medium text-success">
              Qaror: {ACTION_LABEL[item.resolutionAction]}
            </p>
          )}
        </div>
      </div>

      {!resolved && expanded && (
        <div className="mt-4 space-y-3 border-t border-border/60 pt-4">
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Izoh (ixtiyoriy)…"
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-xs outline-none focus:border-primary"
          />
          <div className="flex flex-wrap gap-2">
            {availableActions.map((action) => (
              <button
                key={action}
                type="button"
                disabled={busyAction !== null}
                onClick={() => apply(action)}
                className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold transition disabled:opacity-50 ${
                  action === "DISMISS"
                    ? "bg-muted text-muted-foreground hover:bg-muted/70"
                    : "bg-destructive/10 text-destructive hover:bg-destructive/20"
                }`}
              >
                {busyAction === action && <Loader2 className="size-3.5 animate-spin" />}
                {ACTION_LABEL[action]}
              </button>
            ))}
          </div>
        </div>
      )}
      {error && <p className="mt-2 text-xs text-destructive">{error}</p>}
    </motion.div>
  );
}

function Page() {
  const { data: account } = useMe();
  const [statusFilter, setStatusFilter] = useState<ModerationCaseStatus | "">("OPEN");
  const [subjectFilter, setSubjectFilter] = useState<ModerationSubjectType | "">("");

  const { data, isLoading, error } = useQuery({
    queryKey: ["admin", "moderation-queue", statusFilter, subjectFilter],
    queryFn: () =>
      moderationApi.listQueue({
        status: statusFilter || undefined,
        subjectType: subjectFilter || undefined,
        limit: 50,
      }),
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
          <h1 className="font-display text-3xl font-semibold tracking-tight">Moderatsiya</h1>
          <p className="mt-2 max-w-xl text-sm text-muted-foreground">
            Shikoyat qilingan e'lonlar, profillar, suhbatlar va foydalanuvchilar bo'yicha qaror
            qabul qiling.
          </p>
        </motion.div>

        <section className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <StatCard
            icon={Inbox}
            label="Ko'rsatilmoqda"
            value={items.length}
            accent="primary"
            index={0}
          />
          <StatCard
            icon={Flag}
            label="Foydalanuvchi shikoyati"
            value={items.filter((i) => i.originType === "USER_REPORT").length}
            accent="warning"
            index={1}
          />
          <StatCard
            icon={Bot}
            label="Avtomatik aniqlangan"
            value={items.filter((i) => i.originType === "AUTOMATED_FLAG").length}
            accent="info"
            index={2}
          />
        </section>

        <SectionCard
          title="Filtr"
          icon={Megaphone}
          index={0}
          action={
            <div className="flex flex-wrap items-center gap-2">
              {(["OPEN", "IN_REVIEW", "RESOLVED", ""] as const).map((s) => (
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
          <div className="flex flex-wrap gap-2">
            {(["", "LISTING", "PROFILE", "USER", "CONVERSATION"] as const).map((s) => (
              <button
                key={s || "all-subjects"}
                type="button"
                onClick={() => setSubjectFilter(s)}
                className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${
                  subjectFilter === s
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-muted-foreground hover:bg-primary/10 hover:text-primary"
                }`}
              >
                {s === "" ? "Barcha turlar" : SUBJECT_LABEL[s]}
              </button>
            ))}
          </div>
        </SectionCard>

        <SectionCard title="Navbat" icon={Inbox} index={1}>
          {isLoading && (
            <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" /> Yuklanmoqda…
            </div>
          )}

          {error instanceof ApiError && error.status === 403 && (
            <div className="flex items-start gap-3 rounded-2xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
              <ShieldAlert className="mt-0.5 size-5 shrink-0" />
              Bu sahifa faqat moderatorlik huquqiga ega adminlar uchun.
            </div>
          )}

          {data && items.length === 0 && (
            <EmptyState
              icon={Inbox}
              title="Navbat bo'sh"
              description="Tanlangan filtrga mos moderatsiya holati yo'q."
            />
          )}

          <div className="space-y-4">
            {items.map((item, i) => (
              <CaseRow key={item.id} item={item} index={i} />
            ))}
          </div>
        </SectionCard>
      </div>
    </DashboardShell>
  );
}
