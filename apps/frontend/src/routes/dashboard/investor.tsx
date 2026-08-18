import { createFileRoute, Link } from "@tanstack/react-router";
import { motion } from "framer-motion";
import {
  AreaChart,
  Area,
  XAxis,
  ResponsiveContainer,
  Tooltip as RTooltip,
  PieChart,
  Pie,
  Cell,
} from "recharts";
import { TrendingUp, Wallet, MapPin, Info, Layers, ArrowUpRight } from "lucide-react";
import { requireAuth } from "@/lib/require-auth";
import { DashboardShell } from "@/components/layout/DashboardShell";
import { Container } from "@/components/layout/Container";
import { ReviewGate } from "@/components/auth/ReviewGate";
import { StatCard } from "@/components/dashboard/StatCard";
import { SectionCard } from "@/components/dashboard/SectionCard";
import { useMe } from "@/features/auth/useAuth";
import { formatNumber } from "@/lib/format";

export const Route = createFileRoute("/dashboard/investor")({
  beforeLoad: requireAuth,
  head: () => ({
    meta: [
      { title: "Investor paneli — ActiveHome" },
      { name: "description", content: "Investitsiya imkoniyatlari va portfelingiz." },
    ],
  }),
  component: Page,
});

/** Namunaviy (illustrative) tarkib -- backendda hali "investitsiya loyihasi" degan alohida
 * konsepsiya yo'q (catalog moduli faqat e'lonlar uchun). Real ma'lumotga almashtirish uchun
 * shu massivni bitta so'rov natijasiga almashtirish kifoya. */
const OPPORTUNITIES = [
  {
    name: "Tashkent City — turar-joy kompleksi",
    city: "Toshkent",
    target: 2_500_000_000,
    raised: 1_680_000_000,
    roi: "18%",
  },
  {
    name: "Samarqand savdo markazi",
    city: "Samarqand",
    target: 1_200_000_000,
    raised: 420_000_000,
    roi: "14%",
  },
  {
    name: "Buxoro mehmonxona loyihasi",
    city: "Buxoro",
    target: 900_000_000,
    raised: 810_000_000,
    roi: "21%",
  },
];

const PORTFOLIO_TREND = [
  { m: "Yan", v: 0 },
  { m: "Fev", v: 0 },
  { m: "Mar", v: 0 },
  { m: "Apr", v: 0 },
  { m: "May", v: 0 },
  { m: "Iyun", v: 0 },
];

const ALLOCATION = [
  { name: "Turar-joy", value: 45, color: "oklch(0.55 0.18 275)" },
  { name: "Savdo", value: 30, color: "oklch(0.7 0.16 200)" },
  { name: "Mehmonxona", value: 25, color: "oklch(0.75 0.16 80)" },
];

function Page() {
  const { data: account } = useMe();
  if (!account) return null;

  return (
    <DashboardShell account={account}>
      <ReviewGate account={account}>
        <Container wide className="space-y-8 py-8">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
            className="relative overflow-hidden rounded-3xl border border-border bg-card p-8 shadow-soft"
          >
            <div className="gradient-mesh absolute inset-0 -z-10 opacity-70" />
            <h1 className="font-display text-3xl font-semibold tracking-tight">
              Xush kelibsiz, {account.displayName || "Investor"}
            </h1>
            <p className="mt-2 max-w-xl text-sm text-muted-foreground">
              Investor paneli. Quyidagi imkoniyatlar namunaviy tarkib — haqiqiy loyihalar
              qo'shilgach shu yerda ko'rinadi.
            </p>
          </motion.div>

          <div className="flex items-start gap-3 rounded-2xl border border-primary/20 bg-primary/5 p-4 text-sm text-foreground/80">
            <Info className="mt-0.5 size-4 shrink-0 text-primary" />
            Bu bo'lim namuna sifatida tuzilgan — platformada hali investitsiya loyihalari moduli
            ishga tushirilmagan.
          </div>

          <section className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <StatCard
              icon={Wallet}
              label="Portfel qiymati"
              value={`${formatNumber(0)} so'm`}
              accent="primary"
              index={0}
            />
            <StatCard icon={Layers} label="Faol loyihalar" value={0} accent="info" index={1} />
            <StatCard icon={TrendingUp} label="O'rtacha ROI" value="—" accent="success" index={2} />
          </section>

          <div className="grid gap-6 lg:grid-cols-3">
            <SectionCard
              title="Portfel dinamikasi"
              icon={TrendingUp}
              className="lg:col-span-2"
              index={0}
            >
              <div className="h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={PORTFOLIO_TREND} margin={{ left: -20 }}>
                    <defs>
                      <linearGradient id="portfolio" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="var(--primary)" stopOpacity={0.35} />
                        <stop offset="100%" stopColor="var(--primary)" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <XAxis dataKey="m" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
                    <RTooltip
                      contentStyle={{
                        borderRadius: 12,
                        border: "1px solid var(--border)",
                        background: "var(--card)",
                        fontSize: 12,
                      }}
                    />
                    <Area
                      type="monotone"
                      dataKey="v"
                      stroke="var(--primary)"
                      strokeWidth={2}
                      fill="url(#portfolio)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
              <p className="mt-2 text-center text-xs text-muted-foreground">
                Hali faol investitsiya yo'q — birinchi loyihaga qo'shilgach grafik yangilanadi.
              </p>
            </SectionCard>

            <SectionCard title="Taqsimot" icon={Layers} index={1}>
              <div className="h-40">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={ALLOCATION}
                      dataKey="value"
                      nameKey="name"
                      innerRadius={40}
                      outerRadius={65}
                      paddingAngle={3}
                    >
                      {ALLOCATION.map((a) => (
                        <Cell key={a.name} fill={a.color} />
                      ))}
                    </Pie>
                    <RTooltip
                      contentStyle={{
                        borderRadius: 12,
                        border: "1px solid var(--border)",
                        background: "var(--card)",
                        fontSize: 12,
                      }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div className="mt-2 space-y-1.5">
                {ALLOCATION.map((a) => (
                  <div key={a.name} className="flex items-center justify-between text-xs">
                    <span className="flex items-center gap-1.5 text-muted-foreground">
                      <span className="size-2 rounded-full" style={{ background: a.color }} />{" "}
                      {a.name}
                    </span>
                    <span className="font-semibold text-foreground">{a.value}%</span>
                  </div>
                ))}
              </div>
            </SectionCard>
          </div>

          <SectionCard title="Investitsiya imkoniyatlari" icon={TrendingUp} index={2}>
            <div className="space-y-4">
              {OPPORTUNITIES.map((o) => {
                const pct = Math.round((o.raised / o.target) * 100);
                return (
                  <div
                    key={o.name}
                    className="group rounded-2xl border border-border/70 bg-background/50 p-5 transition hover:border-primary/30 hover:bg-background"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="font-display text-base font-semibold text-foreground">
                          {o.name}
                        </div>
                        <div className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
                          <MapPin className="size-3.5" /> {o.city}
                        </div>
                      </div>
                      <span className="rounded-full bg-success/10 px-3 py-1 text-xs font-semibold text-success">
                        Taxminiy ROI {o.roi}
                      </span>
                    </div>
                    <div className="mt-4 h-2 overflow-hidden rounded-full bg-muted">
                      <motion.div
                        initial={{ width: 0 }}
                        animate={{ width: `${pct}%` }}
                        transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
                        className="h-full rounded-full bg-primary"
                      />
                    </div>
                    <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
                      <span>
                        {formatNumber(o.raised)} / {formatNumber(o.target)} so'm
                      </span>
                      <span className="font-semibold text-foreground">{pct}%</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </SectionCard>

          <p className="text-center text-xs text-muted-foreground">
            Savollaringiz bo'lsa{" "}
            <Link
              to="/contact"
              className="inline-flex items-center gap-1 font-semibold text-primary hover:underline"
            >
              qo'llab-quvvatlash <ArrowUpRight className="size-3" />
            </Link>{" "}
            xizmatiga murojaat qiling.
          </p>
        </Container>
      </ReviewGate>
    </DashboardShell>
  );
}
