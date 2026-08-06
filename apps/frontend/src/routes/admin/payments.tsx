import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CreditCard, Check, X, Loader2, Inbox } from "lucide-react";
import { requireAdmin } from "@/lib/require-auth";
import { DashboardShell } from "@/components/layout/DashboardShell";
import { SectionCard } from "@/components/dashboard/SectionCard";
import { EmptyState } from "@/components/dashboard/EmptyState";
import { useMe } from "@/features/auth/useAuth";
import { ApiError } from "@/lib/http";
import { billingApi, type Invoice } from "@/lib/billing-client";

export const Route = createFileRoute("/admin/payments")({
  beforeLoad: requireAdmin,
  ssr: false,
  head: () => ({ meta: [{ title: "To'lovlarni tasdiqlash — ActiveHome Admin" }] }),
  component: Page,
});

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("uz-UZ", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function InvoiceRow({ invoice }: { invoice: Invoice }) {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState<"confirm" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const decide = async (confirmed: boolean) => {
    setBusy(confirmed ? "confirm" : "reject");
    setError(null);
    try {
      await billingApi.confirmInvoicePayment(invoice.id, { confirmed });
      await queryClient.invalidateQueries({ queryKey: ["billing", "admin-invoices"] });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Amalni bajarib bo'lmadi.");
      setBusy(null);
    }
  };

  return (
    <div className="flex items-center justify-between gap-4 px-6 py-4">
      <div>
        <p className="text-sm font-semibold text-foreground">№{invoice.invoiceNumber}</p>
        <p className="text-xs text-muted-foreground">
          {Number(invoice.amount.amount).toLocaleString("uz-UZ")} {invoice.amount.currency} ·{" "}
          {formatDate(invoice.issuedAt)}
        </p>
        {error && <p className="mt-1 text-xs text-destructive">{error}</p>}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <button
          type="button"
          onClick={() => decide(true)}
          disabled={busy !== null}
          className="inline-flex items-center gap-1.5 rounded-full bg-success px-3.5 py-1.5 text-xs font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
        >
          {busy === "confirm" ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <Check className="size-3.5" />
          )}
          Tasdiqlash
        </button>
        <button
          type="button"
          onClick={() => decide(false)}
          disabled={busy !== null}
          className="inline-flex items-center gap-1.5 rounded-full border border-border px-3.5 py-1.5 text-xs font-medium text-foreground transition hover:bg-muted disabled:opacity-50"
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
  );
}

function Page() {
  const { data: account } = useMe();
  const {
    data: invoices,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["billing", "admin-invoices"],
    queryFn: () => billingApi.adminListInvoices("ISSUED"),
  });

  return (
    <DashboardShell account={account}>
      <div className="mx-auto max-w-4xl space-y-8 px-4 py-8 lg:px-8">
        <div className="relative overflow-hidden rounded-3xl border border-border bg-card p-8 shadow-soft">
          <div className="gradient-mesh absolute inset-0 -z-10 opacity-70" />
          <div className="mb-2 inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-semibold text-primary">
            <CreditCard className="size-3.5" /> Billing
          </div>
          <h1 className="font-display text-3xl font-semibold tracking-tight">
            To'lovlarni tasdiqlash
          </h1>
          <p className="mt-2 max-w-xl text-sm text-muted-foreground">
            Yuridik shaxslarning obuna to'lovlarini shu yerdan tasdiqlang — tasdiqlangach obuna
            avtomatik faollashadi.
          </p>
        </div>

        <SectionCard title="Kutilayotgan hisob-fakturalar" icon={Inbox} index={0} noPadding>
          {isLoading && (
            <div className="flex items-center gap-2 px-6 py-8 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" /> Yuklanmoqda…
            </div>
          )}
          {error instanceof ApiError && error.status === 403 && (
            <div className="px-6 py-8 text-sm text-destructive">
              Sizda to'lovlarni tasdiqlash uchun ruxsat yo'q.
            </div>
          )}
          {invoices && invoices.length === 0 && (
            <div className="px-6 py-8">
              <EmptyState
                icon={Inbox}
                title="Kutilayotgan to'lov yo'q"
                description="Hozircha tasdiqlash kerak bo'lgan hisob-faktura yo'q."
              />
            </div>
          )}
          <div className="divide-y divide-border/70">
            {invoices?.map((invoice) => (
              <InvoiceRow key={invoice.id} invoice={invoice} />
            ))}
          </div>
        </SectionCard>
      </div>
    </DashboardShell>
  );
}
