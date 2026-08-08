import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  ShieldCheck,
  ClipboardList,
  Layers,
  ChevronRight,
  CreditCard,
  Megaphone,
  Users,
  Flag,
} from "lucide-react";
import { requireAdmin } from "@/lib/require-auth";
import { DashboardShell } from "@/components/layout/DashboardShell";
import { useMe } from "@/features/auth/useAuth";
import { getOwnerPanelSlug, OWNER_PANEL_SLUG_DEFAULT } from "@/lib/owner-admin-client";

export const Route = createFileRoute("/admin/")({
  beforeLoad: requireAdmin,
  // `requireAdmin` only enforces in the browser (no request-scoped cookie forwarding into SSR
  // yet) -- without this, the server would render the full page for anyone who requests this
  // URL, admin or not, before the client-side guard ever gets a chance to redirect them away.
  ssr: false,
  head: () => ({ meta: [{ title: "Admin panel — ActiveHome" }] }),
  component: Page,
});

interface AdminLinkCardProps {
  to: string;
  icon: typeof ClipboardList;
  title: string;
  description: string;
  index: number;
}

function AdminLinkCard({ to, icon: Icon, title, description, index }: AdminLinkCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: index * 0.05, ease: [0.22, 1, 0.36, 1] }}
    >
      <Link
        to={to}
        className="group flex items-center justify-between gap-4 rounded-3xl border border-border bg-card p-6 shadow-soft transition hover:border-primary/40 hover:shadow-elevated"
      >
        <div className="flex items-center gap-4">
          <div className="flex size-12 shrink-0 items-center justify-center rounded-2xl bg-primary/10 text-primary">
            <Icon className="size-5" />
          </div>
          <div>
            <h2 className="font-display text-lg font-semibold text-foreground">{title}</h2>
            <p className="mt-1 max-w-md text-sm text-muted-foreground">{description}</p>
          </div>
        </div>
        <ChevronRight className="size-5 shrink-0 text-muted-foreground transition group-hover:translate-x-0.5 group-hover:text-primary" />
      </Link>
    </motion.div>
  );
}

function Page() {
  const { data: account } = useMe();
  const isSuperAdmin = (account?.roles ?? []).includes("super-admin");
  const { data: ownerPanelSlug = OWNER_PANEL_SLUG_DEFAULT } = useQuery({
    queryKey: ["owner-admin", "panel-slug"],
    queryFn: getOwnerPanelSlug,
    enabled: isSuperAdmin,
    staleTime: 0,
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
          <div className="mb-2 inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-2.5 py-1 text-[11px] font-semibold text-primary">
            <ShieldCheck className="size-3.5" /> {isSuperAdmin ? "Super Admin" : "Administrator"}
          </div>
          <h1 className="font-display text-3xl font-semibold tracking-tight">Admin panel</h1>
          <p className="mt-2 max-w-xl text-sm text-muted-foreground">
            Platformani boshqarish uchun bo'limlar. Sizga ko'rinadigan bo'limlar hisobingiz
            huquqlariga bog'liq.
          </p>
        </motion.div>

        <div className="space-y-4">
          <AdminLinkCard
            to="/admin/registrations"
            icon={ClipboardList}
            title="Ro'yxatdan o'tishlarni ko'rib chiqish"
            description="Yangi jismoniy shaxs, yuridik shaxs va investor akkauntlarining anketasini tasdiqlang yoki rad eting."
            index={0}
          />
          <AdminLinkCard
            to="/admin/payments"
            icon={CreditCard}
            title="To'lovlarni tasdiqlash"
            description="Yuridik shaxslarning obuna to'lovlarini tasdiqlang — obuna avtomatik faollashadi."
            index={1}
          />
          <AdminLinkCard
            to="/admin/users"
            icon={Users}
            title="Foydalanuvchilar"
            description="Barcha akkauntlarni qidiring, bloklang yoki faollashtiring, rol biriktiring."
            index={2}
          />
          <AdminLinkCard
            to="/admin/moderation"
            icon={Flag}
            title="Moderatsiya"
            description="Shikoyat qilingan e'lonlar, profillar va foydalanuvchilar bo'yicha qaror qabul qiling."
            index={3}
          />
          {isSuperAdmin && (
            <AdminLinkCard
              to={`/${ownerPanelSlug}`}
              icon={Layers}
              title="Kategoriyalar va tariflar boshqaruvi"
              description="E'lon kategoriyalari, dinamik maydonlar va barcha tarif turlarini yarating, tahrirlang."
              index={4}
            />
          )}
          {isSuperAdmin && (
            <AdminLinkCard
              to={`/${ownerPanelSlug}/banners`}
              icon={Megaphone}
              title="Bannerlar boshqaruvi"
              description="Banner joylarini belgilang, kampaniyalarni yarating va rejalashtiring."
              index={5}
            />
          )}
        </div>
      </div>
    </DashboardShell>
  );
}
