import { createFileRoute, Link } from "@tanstack/react-router";
import { requireAuth } from "@/lib/require-auth";
import { useQuery, useSuspenseQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  Eye,
  Heart,
  MessageSquare,
  Sparkles,
  ArrowUpRight,
  ShieldCheck,
  Trophy,
  Activity,
  Search,
  Lock,
  CheckCircle2,
  Package,
  Loader2,
  Plus,
} from "lucide-react";
import { DashboardShell } from "@/components/layout/DashboardShell";
import { Container } from "@/components/layout/Container";
import { ReviewGate } from "@/components/auth/ReviewGate";
import { StatCard } from "@/components/dashboard/StatCard";
import { SectionCard } from "@/components/dashboard/SectionCard";
import { EmptyState } from "@/components/dashboard/EmptyState";
import { ListingsTable } from "@/components/dashboard/ListingsTable";
import { PropertyCard } from "@/components/data/PropertyCard";
import { featuredPropertiesOptions } from "@/features/properties/queries";
import { catalogClient } from "@/lib/catalog-client";
import { formatNumber } from "@/lib/format";
import { useMe } from "@/features/auth/useAuth";

export const Route = createFileRoute("/dashboard/")({
  beforeLoad: requireAuth,
  head: () => ({
    meta: [
      { title: "Boshqaruv paneli — ActiveHome" },
      { name: "description", content: "Sizning shaxsiy boshqaruv markazingiz." },
    ],
  }),
  loader: ({ context }) => context.queryClient.ensureQueryData(featuredPropertiesOptions(4)),
  component: DashboardPage,
});

const ACTIVITY = [
  { text: "Andrey K. “Toshkentdagi panoramali kvartira”ni ko'rdi", ago: "2 daqiqa oldin" },
  { text: "Maya R. “Samarqanddagi tarixiy kottej”ni saqladi", ago: "14 daqiqa oldin" },
  { text: "Ali T. “Skyline penthouse” haqida xabar yubordi", ago: "1 soat oldin" },
  { text: "Profilingiz uchun tasdiqlash nishoni tasdiqlandi", ago: "3 soat oldin" },
];

const ACHIEVEMENTS = [
  { label: "Birinchi e'lon", done: true },
  { label: "10 ta saqlangan e'lon", done: true },
  { label: "Tasdiqlangan foydalanuvchi", done: true },
  { label: "1,000 ko'rish", done: false },
  { label: "Birinchi bitim yakunlandi", done: false },
];

function DashboardPage() {
  const { data: account } = useMe();
  const { data: featured = [] } = useSuspenseQuery(featuredPropertiesOptions(4));
  const { data: myListings = [], isLoading: myListingsLoading } = useQuery({
    queryKey: ["catalog", "my-listings"],
    queryFn: () => catalogClient.myListings(50),
  });
  if (!account) return null;

  const firstName = (account.displayName || "Foydalanuvchi").split(" ")[0];

  return (
    <DashboardShell account={account}>
      <ReviewGate account={account}>
        <Container wide className="space-y-8 py-8">
          {/* Hero */}
          <motion.section
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
            className="relative overflow-hidden rounded-3xl border border-border bg-card p-8 shadow-soft"
          >
            <div className="gradient-mesh absolute inset-0 -z-10 opacity-70" />
            <div className="flex flex-wrap items-end justify-between gap-6">
              <div>
                <div className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card/60 px-3 py-1 text-[11px] font-medium uppercase tracking-widest text-foreground/70 backdrop-blur">
                  <ShieldCheck className="size-3 text-success" /> Tasdiqlangan hisob
                </div>
                <h1 className="font-display mt-4 text-3xl font-semibold tracking-tight sm:text-4xl">
                  Xayrli kun, {firstName}
                </h1>
                <p className="mt-2 max-w-xl text-sm text-muted-foreground">
                  Sizga mos yangi e'lonlar va xabarlar shu yerda. Qidiruvni davom ettiring yoki o'z
                  e'loningizni joylashtiring.
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Link
                  to="/properties"
                  className="inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground shadow-soft transition hover:shadow-glow"
                >
                  <Search className="size-4" /> Qidiruvni davom ettirish
                </Link>
                <Link
                  to="/list"
                  className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-4 py-2 text-sm font-semibold text-foreground transition hover:bg-muted"
                >
                  <ArrowUpRight className="size-4 text-primary" /> E'lon joylash
                </Link>
              </div>
            </div>
          </motion.section>

          {/* Stats */}
          <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              icon={Eye}
              label="Bu hafta ko'rishlar"
              value={formatNumber(18430)}
              delta="+12.4%"
              deltaTone="up"
              accent="primary"
              spark={[4, 6, 5, 8, 7, 10, 12]}
              index={0}
            />
            <StatCard
              icon={Heart}
              label="Saqlangan"
              value={formatNumber(842)}
              delta="+3.1%"
              deltaTone="up"
              accent="info"
              spark={[2, 3, 3, 4, 5, 5, 6]}
              index={1}
            />
            <StatCard
              icon={MessageSquare}
              label="Yangi xabarlar"
              value={27}
              delta="+8"
              deltaTone="up"
              accent="success"
              spark={[1, 2, 2, 3, 5, 4, 6]}
              index={2}
            />
            <StatCard
              icon={Sparkles}
              label="AI moslik bahosi"
              value={92}
              suffix="/100"
              delta="+1.2"
              deltaTone="up"
              accent="warning"
              index={3}
            />
          </section>

          <SectionCard
            title="Mening e'lonlarim"
            icon={Package}
            noPadding={myListings.length > 0}
            index={0}
            action={
              <Link to="/list" className="text-sm font-semibold text-primary hover:underline">
                <Plus className="mr-1 inline size-3.5" /> Yangi e'lon
              </Link>
            }
          >
            {myListingsLoading ? (
              <div className="flex items-center gap-2 p-6 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" /> Yuklanmoqda…
              </div>
            ) : (
              <ListingsTable listings={myListings} />
            )}
          </SectionCard>

          <div className="grid gap-6 lg:grid-cols-3">
            <SectionCard title="Faollik" icon={Activity} className="lg:col-span-2" index={1}>
              <ol className="relative space-y-5 border-l border-border pl-5">
                {ACTIVITY.map((a, i) => (
                  <li key={i} className="relative">
                    <span className="absolute -left-[26px] top-1 inline-block size-2.5 rounded-full bg-primary ring-4 ring-background" />
                    <div className="text-sm text-foreground">{a.text}</div>
                    <div className="mt-0.5 text-[11px] text-muted-foreground">{a.ago}</div>
                  </li>
                ))}
              </ol>
            </SectionCard>

            <SectionCard title="Yutuqlar" icon={Trophy} index={2}>
              <div className="space-y-2.5">
                {ACHIEVEMENTS.map((a) => (
                  <div
                    key={a.label}
                    className="flex items-center justify-between rounded-xl border border-border/70 bg-background/50 px-3 py-2.5 transition hover:border-primary/30"
                  >
                    <div className="flex items-center gap-2 text-sm text-foreground">
                      {a.done ? (
                        <CheckCircle2 className="size-3.5 text-success" />
                      ) : (
                        <Lock className="size-3.5 text-muted-foreground" />
                      )}
                      {a.label}
                    </div>
                    <span
                      className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                        a.done ? "bg-success/10 text-success" : "bg-muted text-muted-foreground"
                      }`}
                    >
                      {a.done ? "Ochilgan" : "Yopiq"}
                    </span>
                  </div>
                ))}
              </div>
            </SectionCard>
          </div>

          <SectionCard
            title="So'nggi saqlanganlar"
            description="Siz solishtirayotgan e'lonlar."
            action={
              <Link to="/favorites" className="text-sm font-semibold text-primary hover:underline">
                Barchasi →
              </Link>
            }
            index={3}
          >
            {featured.length === 0 ? (
              <EmptyState
                icon={Heart}
                title="Hali saqlangan e'lon yo'q"
                description="Yoqqan uy yoki xizmatni saqlash uchun yurak belgisini bosing."
                compact
                action={
                  <Link
                    to="/properties"
                    className="mt-1 inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground shadow-soft hover:shadow-glow"
                  >
                    <Search className="size-3.5" /> E'lonlarni ko'rish
                  </Link>
                }
              />
            ) : (
              <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 xl:grid-cols-4">
                {featured.map((p, i) => (
                  <PropertyCard key={p.id} property={p} index={i} />
                ))}
              </div>
            )}
          </SectionCard>
        </Container>
      </ReviewGate>
    </DashboardShell>
  );
}
