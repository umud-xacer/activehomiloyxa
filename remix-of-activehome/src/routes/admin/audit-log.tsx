import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ScrollText, Loader2, ChevronDown, ChevronUp } from "lucide-react";
import { requireAuth } from "@/lib/require-auth";
import { AdminShell } from "@/components/layout/AdminShell";
import { EmptyState } from "@/components/state/EmptyState";
import { adminAuditApi, type AuditEntry, type AuditLogFilters } from "@/lib/admin-audit-api";
import { ApiError } from "@/lib/http";

export const Route = createFileRoute("/admin/audit-log")({
  beforeLoad: requireAuth,
  head: () => ({ meta: [{ title: "Audit log — Admin" }] }),
  component: Page,
});

const INPUT =
  "rounded-full border border-border bg-card px-3.5 py-2 text-xs text-foreground placeholder:text-muted-foreground/60 focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/20";

function EntryRow({ entry }: { entry: AuditEntry }) {
  const [open, setOpen] = useState(false);
  const hasPayload = entry.payload && Object.keys(entry.payload).length > 0;

  return (
    <div className="border-b border-border last:border-0">
      <button
        onClick={() => hasPayload && setOpen((v) => !v)}
        className={`flex w-full flex-col gap-1.5 p-4 text-left sm:flex-row sm:items-center sm:justify-between ${hasPayload ? "cursor-pointer hover:bg-muted/30" : ""}`}
      >
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-semibold text-primary">
              {entry.action}
            </span>
            {entry.targetType && (
              <span className="text-xs text-muted-foreground">
                {entry.targetType}
                {entry.targetId && <span className="font-mono"> #{entry.targetId.slice(0, 8)}</span>}
              </span>
            )}
          </div>
          <div className="mt-1 font-mono text-[11px] text-muted-foreground">
            {entry.actorUserId ? `actor: ${entry.actorUserId}` : "actor: tizim"}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground">
          {new Date(entry.occurredAt).toLocaleString("uz-UZ")}
          {hasPayload && (open ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />)}
        </div>
      </button>
      {open && hasPayload && (
        <pre className="mx-4 mb-4 overflow-x-auto rounded-xl bg-muted/50 p-3 text-[11px] text-foreground/80">
          {JSON.stringify(entry.payload, null, 2)}
        </pre>
      )}
    </div>
  );
}

function Page() {
  const [form, setForm] = useState<AuditLogFilters>({});
  const [filters, setFilters] = useState<AuditLogFilters>({});
  const [pages, setPages] = useState<AuditEntry[][]>([]);
  const [cursor, setCursor] = useState<string | undefined>(undefined);

  const { data, isLoading, error } = useQuery({
    queryKey: ["admin", "audit-log", filters, cursor],
    queryFn: () => adminAuditApi.queryLog({ ...filters, cursor }),
  });

  const items = pages.length > 0 ? pages.flat() : data?.items ?? [];

  const loadMore = () => {
    if (!data) return;
    setPages((prev) => [...prev, data.items]);
    setCursor(data.page.nextCursor ?? undefined);
  };

  const applyFilters = (e: React.FormEvent) => {
    e.preventDefault();
    setPages([]);
    setCursor(undefined);
    setFilters(form);
  };

  return (
    <AdminShell>
      <div className="mb-6">
        <h1 className="font-display text-2xl font-semibold text-foreground">Audit log</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Kim, nima, qachon qildi — barcha admin amallarining o'zgarmas jurnali.
        </p>
      </div>

      <form onSubmit={applyFilters} className="mb-5 flex flex-wrap items-center gap-2.5">
        <input
          value={form.actorUserId ?? ""}
          onChange={(e) => setForm((f) => ({ ...f, actorUserId: e.target.value || undefined }))}
          placeholder="Foydalanuvchi ID"
          className={`${INPUT} w-40 font-mono`}
        />
        <input
          value={form.targetType ?? ""}
          onChange={(e) => setForm((f) => ({ ...f, targetType: e.target.value || undefined }))}
          placeholder="Nishon turi (masalan: Listing)"
          className={`${INPUT} w-44`}
        />
        <input
          value={form.action ?? ""}
          onChange={(e) => setForm((f) => ({ ...f, action: e.target.value || undefined }))}
          placeholder="Amal (masalan: SUSPEND)"
          className={`${INPUT} w-40`}
        />
        <input
          type="date"
          value={form.from?.slice(0, 10) ?? ""}
          onChange={(e) => setForm((f) => ({ ...f, from: e.target.value ? `${e.target.value}T00:00:00Z` : undefined }))}
          className={INPUT}
        />
        <input
          type="date"
          value={form.to?.slice(0, 10) ?? ""}
          onChange={(e) => setForm((f) => ({ ...f, to: e.target.value ? `${e.target.value}T23:59:59Z` : undefined }))}
          className={INPUT}
        />
        <button type="submit" className="rounded-full bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground hover:shadow-glow">
          Filtrlash
        </button>
      </form>

      {error ? (
        <EmptyState
          icon={ScrollText}
          title={error instanceof ApiError && error.problem.status === 403 ? "Ruxsat yo'q" : "Xatolik"}
          description={error instanceof ApiError ? error.problem.detail ?? error.problem.title : String(error)}
        />
      ) : isLoading && items.length === 0 ? (
        <div className="h-64 animate-pulse rounded-2xl bg-muted" />
      ) : items.length === 0 ? (
        <EmptyState icon={ScrollText} title="Yozuv topilmadi" description="Filtrlarni o'zgartirib ko'ring." />
      ) : (
        <>
          <div className="overflow-hidden rounded-2xl border border-border bg-card">
            {items.map((entry) => (
              <EntryRow key={entry.id} entry={entry} />
            ))}
          </div>
          {data?.page.nextCursor && (
            <div className="mt-4 flex justify-center">
              <button
                onClick={loadMore}
                disabled={isLoading}
                className="rounded-full border border-border px-4 py-2 text-sm font-semibold text-foreground hover:bg-muted disabled:opacity-50"
              >
                {isLoading ? <Loader2 className="size-4 animate-spin" /> : "Ko'proq yuklash"}
              </button>
            </div>
          )}
        </>
      )}
    </AdminShell>
  );
}
