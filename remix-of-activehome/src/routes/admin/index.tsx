import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Settings2, ShieldCheck, Flag, Receipt, Megaphone, ArrowRight } from "lucide-react";
import { requireAuth } from "@/lib/require-auth";
import { AdminShell } from "@/components/layout/AdminShell";
import { adminVerificationApi } from "@/lib/admin-verification-api";
import { adminModerationApi } from "@/lib/admin-moderation-api";
import { adminBillingApi } from "@/lib/admin-billing-api";
import { adminAdsApi } from "@/lib/admin-ads-api";
import { ApiError } from "@/lib/http";

export const Route = createFileRoute("/admin/")({
  beforeLoad: requireAuth,
  head: () => ({ meta: [{ title: "Admin panel — ActiveHome" }] }),
  component: Page,
});

function safeCount<T>(fn: () => Promise<T[]>) {
  return async () => {
    try {
      return (await fn()).length;
    } catch (err) {
      if (err instanceof ApiError && err.problem.status === 403) return null;
      throw err;
    }
  };
}

const CARDS = [
  {
    to: "/admin/verification" as const,
    label: "Kutilayotgan tasdiqlashlar",
    icon: ShieldCheck,
    queryKey: ["admin", "count", "verification"],
    queryFn: safeCount(() => adminVerificationApi.listQueue("REQUESTED")),
  },
  {
    to: "/admin/moderation" as const,
    label: "Ochiq moderatsiya holatlari",
    icon: Flag,
    queryKey: ["admin", "count", "moderation"],
    queryFn: safeCount(() => adminModerationApi.listQueue({ status: "OPEN" })),
  },
  {
    to: "/admin/billing" as const,
    label: "Chiqarilgan invoyslar",
    icon: Receipt,
    queryKey: ["admin", "count", "billing"],
    queryFn: safeCount(() => adminBillingApi.listInvoices("ISSUED")),
  },
  {
    to: "/admin/ads" as const,
    label: "Faol reklama kampaniyalari",
    icon: Megaphone,
    queryKey: ["admin", "count", "ads"],
    queryFn: safeCount(() => adminAdsApi.listCampaigns("RUNNING")),
  },
];

function CountCard({ card }: { card: (typeof CARDS)[number] }) {
  const { data, isLoading } = useQuery({ queryKey: card.queryKey, queryFn: card.queryFn });
  const Icon = card.icon;
  return (
    <Link
      to={card.to}
      className="flex items-center justify-between rounded-2xl border border-border bg-card p-5 shadow-soft transition hover:shadow-elevated"
    >
      <div>
        <div className="text-2xl font-semibold text-foreground">
          {isLoading ? "…" : data === null ? "—" : data}
        </div>
        <div className="text-xs text-muted-foreground">{card.label}</div>
        {data === null && <div className="mt-0.5 text-[10px] text-destructive">Ruxsat yo'q</div>}
      </div>
      <Icon className="size-6 text-primary" />
    </Link>
  );
}

function Page() {
  return (
    <AdminShell>
      <div className="mb-8">
        <h1 className="font-display text-2xl font-semibold text-foreground">Admin panel</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Konfiguratsiya, moderatsiya, tasdiqlash, billing va reklama boshqaruvi — bitta joyda.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {CARDS.map((card) => (
          <CountCard key={card.to} card={card} />
        ))}
      </div>

      <div className="mt-8 rounded-2xl border border-border bg-card p-5">
        <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <Settings2 className="size-4 text-primary" /> Konfiguratsiya
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          Kategoriyalar, formalar, rollar, qidiruv sozlamalari va platforma sozlamalarini
          yaratish, tekshirish va nashr qilish.
        </p>
        <Link to="/admin/config" className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline">
          Ochish <ArrowRight className="size-3.5" />
        </Link>
      </div>
    </AdminShell>
  );
}
