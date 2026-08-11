import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { motion } from "framer-motion";
import {
  TrendingUp,
  Users,
  Wallet,
  ShieldCheck,
  FileCheck2,
  BarChart3,
  ArrowUpRight,
  MapPin,
} from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { Container } from "@/components/layout/Container";
import { PageHeader } from "@/components/layout/PageHeader";
import {
  CATEGORY_LABEL,
  formatUzsAmount,
  getInvestmentOpportunities,
  type OpportunityCategory,
} from "@/features/investors/demo-data";

export const Route = createFileRoute("/invest/")({
  head: () => ({
    meta: [
      { title: "Investorlar uchun imkoniyatlar — ActiveHome" },
      {
        name: "description",
        content:
          "Tasdiqlangan qurilish va ko'chmas mulk loyihalariga sarmoya kiriting. Shaffof progress, real ROI ko'rsatkichlari va admin tomonidan tekshirilgan loyihalar.",
      },
    ],
  }),
  component: Page,
});

const FILTERS: { key: OpportunityCategory | "all"; label: string }[] = [
  { key: "all", label: "Barchasi" },
  { key: "residential", label: "Turar-joy" },
  { key: "commercial", label: "Savdo" },
  { key: "hotel", label: "Mehmonxona" },
  { key: "industrial", label: "Sanoat" },
];

const TRUST_POINTS = [
  {
    Icon: ShieldCheck,
    title: "Admin tomonidan tekshirilgan",
    desc: "Har bir investor akkaunti va loyiha ma'lumotnomasi platforma tomonidan qo'lda ko'rib chiqiladi.",
  },
  {
    Icon: BarChart3,
    title: "Shaffof progress",
    desc: "Jalb qilingan mablag', ROI va bosqichlar har doim ochiq ko'rinishda, yashirin shartlar yo'q.",
  },
  {
    Icon: FileCheck2,
    title: "Hujjatlashtirilgan loyihalar",
    desc: "Har bir loyiha yer huquqi va qurilish litsenziyasi tasdiqlangandan so'ng platformaga qo'shiladi.",
  },
];

function OpportunityCard({
  o,
  index,
}: {
  o: Awaited<ReturnType<typeof getInvestmentOpportunities>>[number];
  index: number;
}) {
  const pct = Math.round((o.raised / o.target) * 100);
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.5, delay: Math.min(index * 0.05, 0.4), ease: [0.22, 1, 0.36, 1] }}
    >
      <Link
        to="/invest/$slug"
        params={{ slug: o.slug }}
        className="group flex h-full flex-col overflow-hidden rounded-3xl border border-border bg-card shadow-soft transition-all hover:-translate-y-1 hover:shadow-elevated"
      >
        <div className="relative aspect-[16/10] overflow-hidden">
          <img
            src={o.image}
            alt={o.title}
            loading="lazy"
            className="size-full object-cover transition-transform duration-700 group-hover:scale-[1.06]"
          />
          <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent" />
          <span className="absolute left-3 top-3 rounded-full bg-card/90 px-2.5 py-1 text-[11px] font-semibold text-foreground backdrop-blur">
            {CATEGORY_LABEL[o.category]}
          </span>
          <span className="absolute right-3 top-3 rounded-full bg-success/90 px-2.5 py-1 text-[11px] font-bold text-white backdrop-blur">
            ROI {o.roi}
          </span>
        </div>

        <div className="flex flex-1 flex-col p-5">
          <div className="flex items-center gap-1 text-xs text-muted-foreground">
            <MapPin className="size-3.5" /> {o.city}
          </div>
          <h3 className="font-display mt-1.5 text-lg font-semibold leading-snug text-foreground">
            {o.title}
          </h3>

          <div className="mt-4 h-2 overflow-hidden rounded-full bg-muted">
            <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
          </div>
          <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
            <span>{formatUzsAmount(o.raised)}</span>
            <span className="font-semibold text-foreground">{pct}%</span>
          </div>

          <div className="mt-4 flex items-center justify-between border-t border-border pt-4 text-xs text-muted-foreground">
            <span>Min. {formatUzsAmount(o.minInvestment)}</span>
            <span className="inline-flex items-center gap-1 font-semibold text-primary group-hover:underline">
              Batafsil <ArrowUpRight className="size-3.5" />
            </span>
          </div>
        </div>
      </Link>
    </motion.div>
  );
}

function Page() {
  const { data: opportunities = [] } = useQuery({
    queryKey: ["invest", "opportunities"],
    queryFn: getInvestmentOpportunities,
    staleTime: Infinity,
  });
  const [filter, setFilter] = useState<OpportunityCategory | "all">("all");

  const filtered =
    filter === "all" ? opportunities : opportunities.filter((o) => o.category === filter);

  const totalRaised = opportunities.reduce((sum, o) => sum + o.raised, 0);
  const totalInvestors = opportunities.reduce((sum, o) => sum + o.investorsCount, 0);
  const avgRoi = opportunities.length
    ? Math.round(
        opportunities.reduce((sum, o) => sum + parseFloat(o.roi), 0) / opportunities.length,
      )
    : 0;

  return (
    <AppShell>
      <PageHeader
        eyebrow="Investorlar uchun"
        title="Loyihalarga sarmoya kiriting, o'sishni birga kuzating"
        description="Tasdiqlangan qurilish va ko'chmas mulk loyihalari — shaffof progress, real ROI va admin tomonidan tekshirilgan hujjatlar bilan."
        actions={
          <Link
            to="/auth/sign-up"
            className="group inline-flex items-center gap-1.5 rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground shadow-soft transition hover:shadow-glow"
          >
            Investor sifatida ro'yxatdan o'tish
            <ArrowUpRight className="size-4 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
          </Link>
        }
      />

      <Container wide className="pb-24 pt-10">
        {/* Stats band */}
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div className="rounded-2xl border border-border bg-card p-5 shadow-soft">
            <div className="flex size-9 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <BarChart3 className="size-4" />
            </div>
            <div className="font-display mt-3 text-2xl font-semibold text-foreground">
              {opportunities.length}
            </div>
            <div className="text-xs text-muted-foreground">Faol loyihalar</div>
          </div>
          <div className="rounded-2xl border border-border bg-card p-5 shadow-soft">
            <div className="flex size-9 items-center justify-center rounded-xl bg-success/10 text-success">
              <Wallet className="size-4" />
            </div>
            <div className="font-display mt-3 text-2xl font-semibold text-foreground">
              {formatUzsAmount(totalRaised)}
            </div>
            <div className="text-xs text-muted-foreground">Jami jalb qilingan mablag'</div>
          </div>
          <div className="rounded-2xl border border-border bg-card p-5 shadow-soft">
            <div className="flex size-9 items-center justify-center rounded-xl bg-amber-500/10 text-amber-600">
              <TrendingUp className="size-4" />
            </div>
            <div className="font-display mt-3 text-2xl font-semibold text-foreground">
              {avgRoi}%
            </div>
            <div className="text-xs text-muted-foreground">O'rtacha taxminiy ROI</div>
          </div>
          <div className="rounded-2xl border border-border bg-card p-5 shadow-soft">
            <div className="flex size-9 items-center justify-center rounded-xl bg-sky-500/10 text-sky-600">
              <Users className="size-4" />
            </div>
            <div className="font-display mt-3 text-2xl font-semibold text-foreground">
              {totalInvestors}
            </div>
            <div className="text-xs text-muted-foreground">Faol investorlar</div>
          </div>
        </div>

        {/* Filters */}
        <div className="mt-10 flex flex-wrap gap-2">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={`rounded-full px-4 py-2 text-sm font-medium transition ${
                filter === f.key
                  ? "bg-primary text-primary-foreground shadow-soft"
                  : "border border-border bg-card text-foreground/70 hover:bg-muted"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        {/* Grid */}
        <div className="mt-6 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((o, i) => (
            <OpportunityCard key={o.slug} o={o} index={i} />
          ))}
        </div>

        {/* Trust band */}
        <div className="mt-20 rounded-3xl border border-border bg-card/60 p-8 sm:p-10">
          <h2 className="font-display text-2xl font-semibold text-foreground sm:text-3xl">
            Nega ActiveHome orqali sarmoya kiritish kerak?
          </h2>
          <div className="mt-8 grid gap-6 sm:grid-cols-3">
            {TRUST_POINTS.map((t) => (
              <div key={t.title}>
                <div className="flex size-11 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                  <t.Icon className="size-5" />
                </div>
                <h3 className="font-display mt-4 text-base font-semibold text-foreground">
                  {t.title}
                </h3>
                <p className="mt-1.5 text-sm text-muted-foreground">{t.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </Container>
    </AppShell>
  );
}
