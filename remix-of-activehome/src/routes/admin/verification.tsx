import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Check, X } from "lucide-react";
import { requireAuth } from "@/lib/require-auth";
import { AdminShell } from "@/components/layout/AdminShell";
import { EmptyState } from "@/components/state/EmptyState";
import { adminVerificationApi, type AdminVerificationCase } from "@/lib/admin-verification-api";
import { ApiError } from "@/lib/http";

export const Route = createFileRoute("/admin/verification")({
  beforeLoad: requireAuth,
  head: () => ({ meta: [{ title: "Tasdiqlash navbati — Admin" }] }),
  component: Page,
});

const STATUS_LABEL: Record<string, string> = {
  REQUESTED: "So'ralgan",
  IN_REVIEW: "Tekshiruvda",
  APPROVED: "Tasdiqlangan",
  REJECTED: "Rad etilgan",
};

const queueOptions = {
  queryKey: ["admin", "verification-queue"],
  queryFn: () => adminVerificationApi.listQueue(),
};

function CaseRow({ item }: { item: AdminVerificationCase }) {
  const queryClient = useQueryClient();
  const [reason, setReason] = useState("");
  const mutation = useMutation({
    mutationFn: (outcome: "APPROVED" | "REJECTED") =>
      adminVerificationApi.decide(item.id, outcome, reason || undefined),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "verification-queue"] }),
  });

  const pending = item.status === "REQUESTED" || item.status === "IN_REVIEW";

  return (
    <div className="flex flex-col gap-3 border-b border-border p-5 last:border-0 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <div className="text-sm font-medium text-foreground">Profil #{item.businessProfileId.slice(0, 8)}</div>
        <div className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
          <span className="rounded-full bg-muted px-2 py-0.5 font-semibold">{STATUS_LABEL[item.status]}</span>
          <span>SLA: {new Date(item.slaDueAt).toLocaleDateString()}</span>
        </div>
        {item.decision?.reason && (
          <p className="mt-1 text-xs text-muted-foreground">Sabab: {item.decision.reason}</p>
        )}
      </div>
      {pending && (
        <div className="flex shrink-0 items-center gap-2">
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Izoh (ixtiyoriy)"
            className="w-40 rounded-full border border-border bg-background px-3 py-1.5 text-xs"
          />
          <button
            onClick={() => mutation.mutate("APPROVED")}
            disabled={mutation.isPending}
            className="inline-flex items-center gap-1 rounded-full bg-success/15 px-3 py-1.5 text-xs font-semibold text-success hover:bg-success/25 disabled:opacity-50"
          >
            <Check className="size-3.5" /> Tasdiqlash
          </button>
          <button
            onClick={() => mutation.mutate("REJECTED")}
            disabled={mutation.isPending}
            className="inline-flex items-center gap-1 rounded-full bg-destructive/15 px-3 py-1.5 text-xs font-semibold text-destructive hover:bg-destructive/25 disabled:opacity-50"
          >
            <X className="size-3.5" /> Rad etish
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
        <h1 className="font-display text-2xl font-semibold text-foreground">Tasdiqlash navbati</h1>
        <p className="mt-1 text-sm text-muted-foreground">Biznes-profillarni tasdiqlash yoki rad etish.</p>
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
        <EmptyState title="Navbat bo'sh" description="Hozircha tasdiqlash so'rovlari yo'q." />
      )}
    </AdminShell>
  );
}
