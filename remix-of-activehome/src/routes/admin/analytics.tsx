import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";
import { BarChart3, Users, TrendingUp, AlertCircle } from "lucide-react";
import { requireAuth } from "@/lib/require-auth";
import { AdminShell } from "@/components/layout/AdminShell";
import { listingApi } from "@/lib/listing-api";
import { categoriesOptions } from "@/features/properties/queries";
import { adminUsersApi } from "@/lib/admin-users-api";
import {
  adminReportsApi,
  type ListingsOverviewReport,
  type ModerationThroughputReport,
  type RevenueReport,
  type VerificationSlaReport,
} from "@/lib/admin-reports-api";
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { ApiError } from "@/lib/http";

export const Route = createFileRoute("/admin/analytics")({
  beforeLoad: requireAuth,
  head: () => ({ meta: [{ title: "Analitika — Admin" }] }),
  component: Page,
});

const CHART_CONFIG: ChartConfig = { value: { label: "Qiymat", color: "hsl(var(--primary))" } };

function Card({ title, icon: Icon, children }: { title: string; icon: typeof BarChart3; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-border bg-card p-5 shadow-soft">
      <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-foreground">
        <Icon className="size-4 text-primary" /> {title}
      </div>
      {children}
    </div>
  );
}

function BarStat({ data }: { data: { name: string; value: number }[] }) {
  if (data.every((d) => d.value === 0)) {
    return <div className="flex h-48 items-center justify-center text-xs text-muted-foreground">Bu oraliqda ma'lumot yo'q</div>;
  }
  return (
    <ChartContainer config={CHART_CONFIG} className="h-48 w-full">
      <BarChart data={data}>
        <CartesianGrid vertical={false} strokeDasharray="3 3" />
        <XAxis dataKey="name" tickLine={false} axisLine={false} fontSize={11} interval={0} angle={-20} textAnchor="end" height={50} />
        <YAxis tickLine={false} axisLine={false} fontSize={11} allowDecimals={false} />
        <ChartTooltip content={<ChartTooltipContent />} />
        <Bar dataKey="value" fill="var(--color-value)" radius={4} />
      </BarChart>
    </ChartContainer>
  );
}

/** Real category distribution -- computed client-side from the actual admin listings feed
 * (`listingApi.listListings`, the same source `admin/listings.tsx` uses), since neither
 * `GET /admin/dashboard` nor any `/admin/reports` dataset breaks listings down by category. */
function CategoryDistribution() {
  const { data: categories } = useQuery(categoriesOptions());
  const { data: listings, isLoading } = useQuery({
    queryKey: ["admin", "analytics", "listings-sample"],
    queryFn: () => listingApi.listListings({ limit: 200 }),
  });

  const data = useMemo(() => {
    if (!listings) return [];
    const counts = new Map<string, number>();
    for (const l of listings) {
      const key = l.categoryPath ?? "—";
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return [...counts.entries()]
      .map(([path, value]) => ({
        name: categories?.find((c) => c.path === path)?.name.uz_latn ?? path,
        value,
      }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 10);
  }, [listings, categories]);

  return (
    <Card title="Kategoriyalar bo'yicha taqsimot" icon={BarChart3}>
      {isLoading ? <div className="h-48 animate-pulse rounded-xl bg-muted" /> : <BarStat data={data} />}
      <p className="mt-3 text-[11px] text-muted-foreground">
        So'nggi {listings?.length ?? 0} ta e'lon asosida (top 10 kategoriya).
      </p>
    </Card>
  );
}

/** Real new-user signups per day -- computed client-side from `GET /admin/users` (createdAt),
 * since `newUsers7d` on `GET /admin/dashboard` is always null (nothing populates it yet, see
 * `admin/application/dashboard_use_cases.py`) and no report gives a real time series either. */
function UserGrowth() {
  const { data, isLoading } = useQuery({
    queryKey: ["admin", "analytics", "users-sample"],
    queryFn: () => adminUsersApi.listUsers({ limit: 100 }),
  });

  const data14d = useMemo(() => {
    const days: { name: string; value: number }[] = [];
    const counts = new Map<string, number>();
    for (const u of data?.items ?? []) {
      if (!u.createdAt) continue;
      const day = u.createdAt.slice(5, 10);
      counts.set(day, (counts.get(day) ?? 0) + 1);
    }
    for (let i = 13; i >= 0; i--) {
      const d = new Date();
      d.setDate(d.getDate() - i);
      const key = d.toISOString().slice(5, 10);
      days.push({ name: key, value: counts.get(key) ?? 0 });
    }
    return days;
  }, [data]);

  return (
    <Card title="Ro'yxatdan o'tishlar (so'nggi 14 kun)" icon={Users}>
      {isLoading ? <div className="h-48 animate-pulse rounded-xl bg-muted" /> : <BarStat data={data14d} />}
      <p className="mt-3 text-[11px] text-muted-foreground">
        So'nggi {data?.items.length ?? 0} ta foydalanuvchi (birinchi sahifa) asosida — to'liq tarix emas.
      </p>
    </Card>
  );
}

function isoDaysAgo(days: number) {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

function ReportsSection() {
  const [from, setFrom] = useState(isoDaysAgo(30));
  const [to, setTo] = useState(isoDaysAgo(0));
  const range = { from, to };

  const overview = useQuery({
    queryKey: ["admin", "report", "LISTINGS_OVERVIEW", range],
    queryFn: () => adminReportsApi.getReport<ListingsOverviewReport>("LISTINGS_OVERVIEW", range),
  });
  const revenue = useQuery({
    queryKey: ["admin", "report", "REVENUE", range],
    queryFn: () => adminReportsApi.getReport<RevenueReport>("REVENUE", range),
  });
  const verification = useQuery({
    queryKey: ["admin", "report", "VERIFICATION_SLA", range],
    queryFn: () => adminReportsApi.getReport<VerificationSlaReport>("VERIFICATION_SLA", range),
  });
  const moderation = useQuery({
    queryKey: ["admin", "report", "MODERATION_THROUGHPUT", range],
    queryFn: () => adminReportsApi.getReport<ModerationThroughputReport>("MODERATION_THROUGHPUT", range),
  });

  const anyError = [overview, revenue, verification, moderation].find((q) => q.error)?.error;

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2.5">
        <TrendingUp className="size-4 text-primary" />
        <span className="text-sm font-semibold text-foreground">Hisobotlar</span>
        <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="rounded-full border border-border bg-card px-3 py-1.5 text-xs" />
        <span className="text-xs text-muted-foreground">—</span>
        <input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="rounded-full border border-border bg-card px-3 py-1.5 text-xs" />
      </div>

      {anyError && (
        <div className="mb-4 flex items-center gap-2 rounded-xl border border-destructive/30 bg-destructive/10 px-3.5 py-2.5 text-xs text-destructive">
          <AlertCircle className="size-4 shrink-0" />
          {anyError instanceof ApiError ? anyError.problem.detail ?? anyError.problem.title : String(anyError)}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Card title="E'lonlar bilan bog'liq amallar" icon={BarChart3}>
          {overview.isLoading ? (
            <div className="h-48 animate-pulse rounded-xl bg-muted" />
          ) : (
            <BarStat data={Object.entries(overview.data?.counts ?? {}).map(([name, value]) => ({ name, value }))} />
          )}
        </Card>

        <Card title="Moderatsiya (amal turi bo'yicha)" icon={BarChart3}>
          {moderation.isLoading ? (
            <div className="h-48 animate-pulse rounded-xl bg-muted" />
          ) : (
            <BarStat data={Object.entries(moderation.data?.byVerb ?? {}).map(([name, value]) => ({ name, value }))} />
          )}
        </Card>

        <Card title="Daromad (valyuta bo'yicha)" icon={TrendingUp}>
          {revenue.isLoading ? (
            <div className="h-24 animate-pulse rounded-xl bg-muted" />
          ) : (
            <div className="space-y-2">
              <div className="text-xs text-muted-foreground">
                Tasdiqlangan to'lovlar: <span className="font-semibold text-foreground">{revenue.data?.confirmedPayments ?? 0}</span>
              </div>
              {Object.entries(revenue.data?.totalsByCurrency ?? {}).length === 0 ? (
                <div className="text-xs text-muted-foreground">Bu oraliqda to'lov yo'q</div>
              ) : (
                Object.entries(revenue.data?.totalsByCurrency ?? {}).map(([currency, amount]) => (
                  <div key={currency} className="flex items-center justify-between rounded-lg bg-muted/40 px-3 py-1.5 text-sm">
                    <span className="text-muted-foreground">{currency}</span>
                    <span className="font-semibold text-foreground">{amount.toLocaleString("ru-RU")}</span>
                  </div>
                ))
              )}
            </div>
          )}
        </Card>

        <Card title="Tasdiqlash SLA" icon={Users}>
          {verification.isLoading ? (
            <div className="h-24 animate-pulse rounded-xl bg-muted" />
          ) : (
            <div className="grid grid-cols-3 gap-2 text-center">
              <div className="rounded-lg bg-muted/40 p-3">
                <div className="text-lg font-semibold text-foreground">{verification.data?.decisions ?? 0}</div>
                <div className="text-[10px] text-muted-foreground">Qarorlar</div>
              </div>
              <div className="rounded-lg bg-success/10 p-3">
                <div className="text-lg font-semibold text-success">{verification.data?.approved ?? 0}</div>
                <div className="text-[10px] text-muted-foreground">Tasdiqlangan</div>
              </div>
              <div className="rounded-lg bg-destructive/10 p-3">
                <div className="text-lg font-semibold text-destructive">{verification.data?.rejected ?? 0}</div>
                <div className="text-[10px] text-muted-foreground">Rad etilgan</div>
              </div>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

function Page() {
  return (
    <AdminShell>
      <div className="mb-6">
        <h1 className="font-display text-2xl font-semibold text-foreground">Analitika</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Platforma faoliyati bo'yicha real ma'lumotlar — e'lonlar, foydalanuvchilar va operatsion hisobotlar.
        </p>
      </div>

      <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <CategoryDistribution />
        <UserGrowth />
      </div>

      <ReportsSection />
    </AdminShell>
  );
}
