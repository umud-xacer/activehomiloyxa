import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { requireAuth } from "@/lib/require-auth";
import { AdminShell } from "@/components/layout/AdminShell";
import { EmptyState } from "@/components/state/EmptyState";
import { adminModerationApi, type ModerationAction, type ModerationCase } from "@/lib/admin-moderation-api";
import { ApiError } from "@/lib/http";

export const Route = createFileRoute("/admin/moderation")({
  beforeLoad: requireAuth,
  head: () => ({ meta: [{ title: "Moderatsiya — Admin" }] }),
  component: Page,
});

const ACTIONS: { value: ModerationAction; label: string }[] = [
  { value: "REQUEST_CORRECTION", label: "Tuzatish so'rash" },
  { value: "HIDE", label: "Yashirish" },
  { value: "REJECT", label: "Rad etish" },
  { value: "SUSPEND", label: "Muzlatish" },
  { value: "REMOVE", label: "O'chirish" },
];

const queueOptions = {
  queryKey: ["admin", "moderation-queue"],
  queryFn: () => adminModerationApi.listQueue(),
};

function CaseRow({ item }: { item: ModerationCase }) {
  const queryClient = useQueryClient();
  const [action, setAction] = useState<ModerationAction>("REQUEST_CORRECTION");
  const [note, setNote] = useState("");
  const mutation = useMutation({
    mutationFn: () => adminModerationApi.applyAction(item.id, action, note || undefined),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "moderation-queue"] }),
  });

  return (
    <div className="flex flex-col gap-3 border-b border-border p-5 last:border-0 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <div className="text-sm font-medium text-foreground">
          {item.subjectType} #{item.subjectId.slice(0, 8)}
        </div>
        <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span className="rounded-full bg-muted px-2 py-0.5 font-semibold">{item.status}</span>
          <span>{item.originType}</span>
          {item.reportReason && <span>Sabab: {item.reportReason}</span>}
          {item.ruleKey && <span>Qoida: {item.ruleKey}</span>}
        </div>
        {item.resolutionAction && (
          <p className="mt-1 text-xs text-muted-foreground">Yechim: {item.resolutionAction}</p>
        )}
      </div>
      {item.status !== "RESOLVED" && (
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <select
            value={action}
            onChange={(e) => setAction(e.target.value as ModerationAction)}
            className="rounded-full border border-border bg-background px-3 py-1.5 text-xs"
          >
            {ACTIONS.map((a) => (
              <option key={a.value} value={a.value}>
                {a.label}
              </option>
            ))}
          </select>
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Izoh"
            className="w-32 rounded-full border border-border bg-background px-3 py-1.5 text-xs"
          />
          <button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
            className="rounded-full bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground hover:shadow-glow disabled:opacity-50"
          >
            Qo'llash
          </button>
        </div>
      )}
    </div>
  );
}

function Page() {
  const { data, isLoading, error } = useQuery(queueOptions);

  return (
    <AdminShell>
      <div className="mb-6">
        <h1 className="font-display text-2xl font-semibold text-foreground">Moderatsiya navbati</h1>
        <p className="mt-1 text-sm text-muted-foreground">Belgilangan (flagged) kontent bo'yicha choralar.</p>
      </div>

      {error ? (
        <EmptyState
          title={error instanceof ApiError && error.problem.status === 403 ? "Ruxsat yo'q" : "Xatolik"}
          description={error instanceof ApiError ? error.problem.detail ?? error.problem.title : String(error)}
        />
      ) : isLoading ? (
        <div className="h-40 animate-pulse rounded-2xl bg-muted" />
      ) : data && data.length > 0 ? (
        <div className="rounded-2xl border border-border bg-card">
          {data.map((item) => (
            <CaseRow key={item.id} item={item} />
          ))}
        </div>
      ) : (
        <EmptyState title="Navbat bo'sh" description="Hozircha belgilangan kontent yo'q." />
      )}
    </AdminShell>
  );
}
