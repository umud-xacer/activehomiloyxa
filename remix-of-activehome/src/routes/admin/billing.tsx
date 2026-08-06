import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check } from "lucide-react";
import { requireAuth } from "@/lib/require-auth";
import { AdminShell } from "@/components/layout/AdminShell";
import { EmptyState } from "@/components/state/EmptyState";
import { adminBillingApi, type AdminInvoice } from "@/lib/admin-billing-api";
import { ApiError } from "@/lib/http";

export const Route = createFileRoute("/admin/billing")({
  beforeLoad: requireAuth,
  head: () => ({ meta: [{ title: "Invoyslar — Admin" }] }),
  component: Page,
});

const invoicesOptions = {
  queryKey: ["admin", "invoices"],
  queryFn: () => adminBillingApi.listInvoices(),
};

const STATUS_STYLE: Record<AdminInvoice["status"], string> = {
  ISSUED: "bg-warning/15 text-warning",
  PAID: "bg-success/15 text-success",
  VOID: "bg-muted text-muted-foreground",
};

function InvoiceRow({ invoice }: { invoice: AdminInvoice }) {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => adminBillingApi.confirmPayment(invoice.id, true, "confirmed via admin panel"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "invoices"] }),
  });

  return (
    <div className="flex items-center justify-between border-b border-border p-5 last:border-0">
      <div>
        <div className="text-sm font-medium text-foreground">{invoice.invoiceNumber}</div>
        <div className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
          <span className={`rounded-full px-2 py-0.5 font-semibold ${STATUS_STYLE[invoice.status]}`}>
            {invoice.status}
          </span>
          <span>
            {invoice.amount.amount} {invoice.amount.currency}
          </span>
          <span>{new Date(invoice.issuedAt).toLocaleDateString()}</span>
        </div>
      </div>
      {invoice.status === "ISSUED" && (
        <button
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending}
          className="inline-flex items-center gap-1 rounded-full bg-success/15 px-3 py-1.5 text-xs font-semibold text-success hover:bg-success/25 disabled:opacity-50"
        >
          <Check className="size-3.5" /> To'lovni tasdiqlash
        </button>
      )}
    </div>
  );
}

function Page() {
  const { data, isLoading, error } = useQuery(invoicesOptions);

  return (
    <AdminShell>
      <div className="mb-6">
        <h1 className="font-display text-2xl font-semibold text-foreground">Invoyslar</h1>
        <p className="mt-1 text-sm text-muted-foreground">Offline to'lovlarni tasdiqlash (entitlementlarni faollashtiradi).</p>
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
          {data.map((inv) => (
            <InvoiceRow key={inv.id} invoice={inv} />
          ))}
        </div>
      ) : (
        <EmptyState title="Invoyslar yo'q" description="Hozircha hech qanday buyurtma bo'yicha invoys chiqarilmagan." />
      )}
    </AdminShell>
  );
}
