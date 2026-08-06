import { createFileRoute, Link } from "@tanstack/react-router";
import { requireAuth } from "@/lib/require-auth";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  TrendingUp,
  Eye,
  Heart,
  MessageSquare,
  ArrowUpRight,
  ShieldCheck,
  Trophy,
  Activity,
} from "lucide-react";
import { DashboardShell } from "@/components/layout/DashboardShell";
import { PropertyCard } from "@/components/data/PropertyCard";
import { favoritePropertiesOptions } from "@/features/properties/favorites-queries";
import { formatNumber } from "@/lib/format";

// No SSR `loader` here on purpose -- see favorites.tsx's own note (session token only exists
// client-side; an SSR-time authed fetch 500s the page).
export const Route = createFileRoute("/dashboard/")({
  beforeLoad: requireAuth,
  head: () => ({
    meta: [
      { title: "Dashboard — ActiveHome" },
      { name: "description", content: "Your personal command center." },
    ],
  }),
  component: DashboardPage,
});

const KPI = [
  { label: "Views this week", value: 18430, delta: "+12.4%", icon: Eye, hue: "from-indigo-500/15 to-violet-500/15" },
  { label: "Saved by users", value: 842, delta: "+3.1%", icon: Heart, hue: "from-rose-500/15 to-pink-500/15" },
  { label: "New messages", value: 27, delta: "+8", icon: MessageSquare, hue: "from-emerald-500/15 to-teal-500/15" },
];

const ACTIVITY = [
  { kind: "view", text: "Andrey K. viewed “Panoramic apartment in Tashkent”", ago: "2m ago" },
  { kind: "save", text: "Maya R. saved “Heritage cottage in Samarkand”", ago: "14m ago" },
  { kind: "msg", text: "Ali T. sent a message about “Skyline penthouse”", ago: "1h ago" },
  { kind: "verify", text: "Verification badge approved for your profile", ago: "3h ago" },
  { kind: "offer", text: "Counter-offer of $1.85M received for unit #1204", ago: "Yesterday" },
];

function DashboardPage() {
  const { data: featured = [] } = useQuery(favoritePropertiesOptions(4));

  return (
    <DashboardShell>
      <div className="mx-auto max-w-7xl space-y-10 px-4 py-10 lg:px-8">
        {/* Hero */}
        <motion.section
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
          className="relative overflow-hidden rounded-3xl border border-border bg-card p-8 shadow-soft"
        >
          <div className="gradient-mesh absolute inset-0 -z-10 opacity-70" />
          <div className="flex flex-wrap items-end justify-between gap-6">
            <div>
              <div className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card/60 px-3 py-1 text-[11px] font-medium uppercase tracking-widest text-foreground/70 backdrop-blur">
                <ShieldCheck className="size-3 text-success" /> Verified · Trust 94
              </div>
              <h1 className="font-display mt-4 text-3xl font-semibold tracking-tight sm:text-4xl">
                Good evening, Demo
              </h1>
              <p className="mt-2 max-w-xl text-sm text-muted-foreground">
                Your portfolio is performing 12% better than last week. 3 properties need attention.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Link
                to="/list"
                className="inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground shadow-soft hover:shadow-glow"
              >
                <ArrowUpRight className="size-4" /> List property
              </Link>
            </div>
          </div>
        </motion.section>

        {/* KPIs */}
        <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {KPI.map((k, i) => (
            <motion.div
              key={k.label}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05, duration: 0.5 }}
              className={`relative overflow-hidden rounded-2xl border border-border bg-card p-5 shadow-soft`}
            >
              <div className={`absolute inset-0 bg-gradient-to-br ${k.hue} opacity-60`} />
              <div className="relative">
                <div className="flex items-center justify-between">
                  <div className="flex size-9 items-center justify-center rounded-xl bg-card/80 text-primary shadow-soft backdrop-blur">
                    <k.icon className="size-4" />
                  </div>
                  <span className="inline-flex items-center gap-0.5 rounded-full bg-success/10 px-2 py-0.5 text-[11px] font-semibold text-success">
                    <TrendingUp className="size-3" /> {k.delta}
                  </span>
                </div>
                <div className="font-display mt-4 text-3xl font-semibold tracking-tight text-foreground">
                  {formatNumber(k.value)}
                  {k.suffix && <span className="text-base text-muted-foreground">{k.suffix}</span>}
                </div>
                <div className="mt-1 text-xs text-muted-foreground">{k.label}</div>
              </div>
            </motion.div>
          ))}
        </section>

        <div className="grid gap-6 lg:grid-cols-3">
          {/* Activity */}
          <section className="rounded-3xl border border-border bg-card p-6 shadow-soft lg:col-span-2">
            <div className="mb-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Activity className="size-4 text-primary" />
                <h2 className="font-display text-lg font-semibold">Activity timeline</h2>
              </div>
              <button className="text-xs font-medium text-muted-foreground hover:text-foreground">
                View all
              </button>
            </div>
            <ol className="relative space-y-5 border-l border-border pl-5">
              {ACTIVITY.map((a, i) => (
                <li key={i} className="relative">
                  <span className="absolute -left-[26px] top-1 inline-block size-2.5 rounded-full bg-primary ring-4 ring-background" />
                  <div className="text-sm text-foreground">{a.text}</div>
                  <div className="mt-0.5 text-[11px] text-muted-foreground">{a.ago}</div>
                </li>
              ))}
            </ol>
          </section>

          {/* Achievements */}
          <section className="rounded-3xl border border-border bg-card p-6 shadow-soft">
            <div className="mb-4 flex items-center gap-2">
              <Trophy className="size-4 text-primary" />
              <h2 className="font-display text-lg font-semibold">Achievements</h2>
            </div>
            <div className="space-y-3">
              {[
                { label: "First listing", done: true },
                { label: "10 favorites earned", done: true },
                { label: "Verified seller", done: true },
                { label: "1,000 views", done: false },
                { label: "First sale closed", done: false },
              ].map((a) => (
                <div key={a.label} className="flex items-center justify-between rounded-xl border border-border bg-background/50 px-3 py-2.5">
                  <div className="text-sm text-foreground">{a.label}</div>
                  <span
                    className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                      a.done ? "bg-success/10 text-success" : "bg-muted text-muted-foreground"
                    }`}
                  >
                    {a.done ? "Unlocked" : "Locked"}
                  </span>
                </div>
              ))}
            </div>
          </section>
        </div>

        {/* Favorites preview */}
        <section>
          <div className="mb-4 flex items-end justify-between">
            <div>
              <h2 className="font-display text-2xl font-semibold tracking-tight">Recently favorited</h2>
              <p className="text-sm text-muted-foreground">
                The four properties you've been comparing.
              </p>
            </div>
            <Link to="/favorites" className="text-sm font-semibold text-primary hover:underline">
              All favorites →
            </Link>
          </div>
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 xl:grid-cols-4">
            {featured.map((p, i) => (
              <PropertyCard key={p.id} property={p} index={i} />
            ))}
          </div>
        </section>
      </div>
    </DashboardShell>
  );
}
