import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Wallet as WalletIcon, ShieldCheck, Clock } from "lucide-react";
import { requireAuth } from "@/lib/require-auth";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/state/EmptyState";
import { billingApi } from "@/lib/billing-api";
import { formatCurrency, formatRelativeDate } from "@/lib/format";
import type { Currency } from "@/features/properties/types";

export const Route = createFileRoute("/wallet")({
  beforeLoad: requireAuth,
  head: () => ({
    meta: [
      { title: "Wallet — ActiveHome" },
      { name: "description", content: "Manage balances, cards and rewards." },
    ],
  }),
  component: Page,
});

const entitlementsOptions = { queryKey: ["entitlements"], queryFn: () => billingApi.listMyEntitlements() };
const ordersOptions = { queryKey: ["orders"], queryFn: () => billingApi.listMyOrders() };

const STATUS_COLOR: Record<string, string> = {
  ACTIVE: "text-success bg-success/10",
  EXPIRED: "text-muted-foreground bg-muted",
  REVOKED: "text-destructive bg-destructive/10",
  PENDING: "text-amber-600 bg-amber-500/10",
  INVOICED: "text-primary bg-primary/10",
  PAID: "text-success bg-success/10",
  FULFILLED: "text-success bg-success/10",
  CANCELLED: "text-destructive bg-destructive/10",
};

function Page() {
  const { data: entitlements, isLoading: loadingEnt } = useQuery(entitlementsOptions);
  const { data: orders, isLoading: loadingOrders } = useQuery(ordersOptions);

  return (
    <AppShell>
      <PageHeader eyebrow="Money" title="Wallet" description="Manage balances, cards and rewards." />
      <div className="mx-auto max-w-4xl space-y-8 px-6 py-12">
        <section>
          <h2 className="font-display mb-4 text-lg font-semibold text-foreground">Faol imtiyozlar</h2>
          {loadingEnt ? (
            <div className="h-24 animate-pulse rounded-2xl bg-muted" />
          ) : !entitlements || entitlements.length === 0 ? (
            <EmptyState icon={ShieldCheck} title="Imtiyozlar yo'q" description="Hozircha faol reja yoki imtiyoz yo'q." />
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {entitlements.map((e) => (
                <div key={e.id} className="rounded-2xl border border-border bg-card p-4 shadow-soft">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold text-foreground">{e.entitlementType.replace(/_/g, " ")}</span>
                    <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${STATUS_COLOR[e.activationState]}`}>
                      {e.activationState}
                    </span>
                  </div>
                  <div className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground">
                    <Clock className="size-3.5" />
                    {formatRelativeDate(e.validUntil)} gacha
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        <section>
          <h2 className="font-display mb-4 text-lg font-semibold text-foreground">Buyurtmalar tarixi</h2>
          {loadingOrders ? (
            <div className="h-24 animate-pulse rounded-2xl bg-muted" />
          ) : !orders || orders.length === 0 ? (
            <EmptyState icon={WalletIcon} title="Buyurtmalar yo'q" description="Hali hech narsa sotib olinmagan." />
          ) : (
            <div className="overflow-hidden rounded-2xl border border-border">
              {orders.map((o) => (
                <div key={o.id} className="flex items-center justify-between border-b border-border bg-card px-4 py-3 last:border-b-0">
                  <div>
                    <div className="text-sm font-semibold text-foreground">#{o.id.slice(0, 8)}</div>
                    <div className="text-xs text-muted-foreground">{formatRelativeDate(o.createdAt)}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-semibold text-foreground">
                      {formatCurrency(Number(o.amount.amount), o.amount.currency as Currency)}
                    </div>
                    <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${STATUS_COLOR[o.status]}`}>
                      {o.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </AppShell>
  );
}
