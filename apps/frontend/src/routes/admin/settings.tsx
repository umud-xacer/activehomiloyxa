import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  Settings as SettingsIcon,
  CreditCard,
  CheckCircle2,
  XCircle,
  Megaphone,
  ChevronRight,
} from "lucide-react";
import { requireAdmin } from "@/lib/require-auth";
import { DashboardShell } from "@/components/layout/DashboardShell";
import { SectionCard } from "@/components/dashboard/SectionCard";
import { billingApi } from "@/lib/billing-client";
import { getOwnerPanelSlug, OWNER_PANEL_SLUG_DEFAULT } from "@/lib/owner-admin-client";
import { useMe } from "@/features/auth/useAuth";

export const Route = createFileRoute("/admin/settings")({
  beforeLoad: requireAdmin,
  ssr: false,
  head: () => ({ meta: [{ title: "Tizim sozlamalari — ActiveHome Admin" }] }),
  component: Page,
});

function ProviderRow({
  name,
  configured,
  note,
}: {
  name: string;
  configured: boolean;
  note?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-xl border border-border/70 px-4 py-3">
      <div>
        <p className="text-sm font-semibold text-foreground">{name}</p>
        {note && <p className="text-xs text-muted-foreground">{note}</p>}
      </div>
      <span
        className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ${
          configured ? "bg-success/10 text-success" : "bg-muted text-muted-foreground"
        }`}
      >
        {configured ? <CheckCircle2 className="size-3.5" /> : <XCircle className="size-3.5" />}
        {configured ? "Kalit o'rnatilgan / Faol" : "Kalit kiritilmagan / Faol emas"}
      </span>
    </div>
  );
}

function Page() {
  const { data: account } = useMe();
  const { data: status, isLoading } = useQuery({
    queryKey: ["admin", "payment-provider-status"],
    queryFn: billingApi.adminGetPaymentProviderStatus,
  });
  const { data: ownerPanelSlug = OWNER_PANEL_SLUG_DEFAULT } = useQuery({
    queryKey: ["owner-admin", "panel-slug"],
    queryFn: getOwnerPanelSlug,
  });

  return (
    <DashboardShell account={account}>
      <div className="mx-auto max-w-4xl space-y-8 px-4 py-8 lg:px-8">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          className="relative overflow-hidden rounded-3xl border border-border bg-card p-8 shadow-soft"
        >
          <div className="gradient-mesh absolute inset-0 -z-10 opacity-70" />
          <h1 className="font-display text-3xl font-semibold tracking-tight">Tizim sozlamalari</h1>
          <p className="mt-2 max-w-xl text-sm text-muted-foreground">
            To'lov provayderlari holati va bosh sahifa bannerlarini boshqarish.
          </p>
        </motion.div>

        <SectionCard
          title="To'lov provayderlari"
          icon={CreditCard}
          description="Maxfiy API kalitlari faqat serverdagi .env faylida saqlanadi — xavfsizlik uchun bu yerda faqat holat ko'rsatiladi, kalitning o'zi kiritilmaydi."
          index={0}
          noPadding
        >
          <div className="space-y-3 p-6">
            {isLoading ? (
              <p className="text-sm text-muted-foreground">Yuklanmoqda…</p>
            ) : (
              <>
                <ProviderRow
                  name="Payme"
                  configured={!!status?.paymeConfigured}
                  note="PAYME_SECRET_KEY (.env) + VITE_PAYME_MERCHANT_ID (frontend)"
                />
                <ProviderRow
                  name="Click"
                  configured={!!status?.clickConfigured}
                  note="CLICK_SECRET_KEY (.env) + VITE_CLICK_SERVICE_ID/VITE_CLICK_MERCHANT_ID (frontend)"
                />
                <ProviderRow
                  name="Uzum Pay"
                  configured={false}
                  note="Real integratsiya hali qurilmagan — Uzum Pay'ning rasmiy merchant API hujjatlari kelganda qo'shiladi."
                />
                <ProviderRow
                  name="Demo/Mock to'lov"
                  configured={!!status?.mockEnabled}
                  note="PAYMENT_PROVIDER=mock (.env) — sinov uchun instant to'lov."
                />
              </>
            )}
          </div>
        </SectionCard>

        <SectionCard title="Bosh sahifa bannerlari" icon={Megaphone} index={1}>
          <Link
            to="/$ownerAdminSlug/banners"
            params={{ ownerAdminSlug: ownerPanelSlug }}
            className="inline-flex items-center gap-2 rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground shadow-soft transition hover:shadow-glow"
          >
            <SettingsIcon className="size-4" /> Bannerlarni boshqarish
            <ChevronRight className="size-4" />
          </Link>
        </SectionCard>
      </div>
    </DashboardShell>
  );
}
