import { createFileRoute, Link, notFound } from "@tanstack/react-router";
import { useSuspenseQuery, useQuery, queryOptions } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  MapPin,
  TrendingUp,
  Wallet,
  Users,
  CalendarClock,
  Timer,
  ArrowUpRight,
  CheckCircle2,
  ArrowLeft,
} from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { Container } from "@/components/layout/Container";
import { PageHeader } from "@/components/layout/PageHeader";
import type { MapMarker } from "@/components/map/YandexMapView";
import { ListingLocationSection } from "@/components/listing/ListingLocationSection";
import {
  CATEGORY_LABEL,
  formatUzsAmount,
  getInvestmentOpportunities,
  getInvestmentOpportunity,
} from "@/features/investors/demo-data";

const opportunityOptions = (slug: string) =>
  queryOptions({
    queryKey: ["invest", "opportunity", slug],
    queryFn: () => getInvestmentOpportunity(slug),
  });

export const Route = createFileRoute("/invest/$slug")({
  loader: async ({ context, params }) => {
    const data = await context.queryClient.ensureQueryData(opportunityOptions(params.slug));
    if (!data) throw notFound();
    return data;
  },
  head: ({ loaderData }) => ({
    meta: loaderData
      ? [
          { title: `${loaderData.title} — Investorlar — ActiveHome` },
          { name: "description", content: loaderData.description },
        ]
      : [{ title: "Loyiha topilmadi — ActiveHome" }],
  }),
  component: Page,
});

function Page() {
  const { slug } = Route.useParams();
  const { data: o } = useSuspenseQuery(opportunityOptions(slug));
  const { data: all = [] } = useQuery({
    queryKey: ["invest", "opportunities"],
    queryFn: getInvestmentOpportunities,
    staleTime: Infinity,
  });

  if (!o) return null;

  const pct = Math.round((o.raised / o.target) * 100);
  const marker: MapMarker = {
    id: o.slug,
    lat: o.lat,
    lng: o.lng,
    label: CATEGORY_LABEL[o.category],
    title: o.title,
    subtitle: o.city,
  };
  const related = all.filter((r) => r.slug !== o.slug).slice(0, 3);

  return (
    <AppShell>
      <PageHeader
        crumbs={[
          { label: "Bosh sahifa", to: "/" },
          { label: "Investorlar", to: "/invest" },
          { label: o.title },
        ]}
        eyebrow={CATEGORY_LABEL[o.category]}
        title={o.title}
        description={o.city}
      />

      <Container wide className="pb-24 pt-10">
        <Link
          to="/invest"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground transition hover:text-foreground"
        >
          <ArrowLeft className="size-3.5" /> Barcha loyihalar
        </Link>

        <div className="mt-6 grid gap-8 lg:grid-cols-[1fr_380px]">
          {/* Main column */}
          <div className="space-y-8">
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
              className="relative aspect-[16/9] overflow-hidden rounded-3xl border border-border shadow-elevated"
            >
              <img src={o.image} alt={o.title} className="size-full object-cover" />
              <div className="absolute inset-0 bg-gradient-to-t from-black/50 via-transparent to-transparent" />
              <span className="absolute right-4 top-4 rounded-full bg-success px-3 py-1.5 text-xs font-bold text-white shadow-soft">
                Taxminiy ROI {o.roi}
              </span>
            </motion.div>

            <div>
              <h2 className="font-display text-2xl font-semibold text-foreground">Loyiha haqida</h2>
              <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{o.description}</p>
            </div>

            <div>
              <h2 className="font-display text-xl font-semibold text-foreground">
                Asosiy jihatlar
              </h2>
              <ul className="mt-4 space-y-3">
                {o.highlights.map((h) => (
                  <li key={h} className="flex items-start gap-2.5 text-sm text-foreground/85">
                    <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" />
                    {h}
                  </li>
                ))}
              </ul>
            </div>

            <div>
              <ListingLocationSection marker={marker} address={o.city} height="360px" />
            </div>
          </div>

          {/* Sticky investment card */}
          <div className="lg:sticky lg:top-24 lg:self-start">
            <div className="rounded-3xl border border-border bg-card p-6 shadow-elevated">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Jalb qilingan</span>
                <span className="font-semibold text-foreground">{pct}%</span>
              </div>
              <div className="mt-2 h-2.5 overflow-hidden rounded-full bg-muted">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${pct}%` }}
                  transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
                  className="h-full rounded-full bg-primary"
                />
              </div>
              <div className="mt-1.5 flex items-center justify-between text-xs text-muted-foreground">
                <span>{formatUzsAmount(o.raised)}</span>
                <span>{formatUzsAmount(o.target)}</span>
              </div>

              <div className="mt-6 space-y-4 border-t border-border pt-5">
                <Stat
                  icon={Wallet}
                  label="Minimal sarmoya"
                  value={formatUzsAmount(o.minInvestment)}
                />
                <Stat icon={TrendingUp} label="Taxminiy ROI" value={o.roi} />
                <Stat icon={Timer} label="Loyiha muddati" value={`${o.durationMonths} oy`} />
                <Stat icon={CalendarClock} label="Yakunlanish sanasi" value={o.completionDate} />
                <Stat icon={Users} label="Faol investorlar" value={String(o.investorsCount)} />
                <Stat icon={MapPin} label="Shahar" value={o.city} />
              </div>

              <Link
                to="/auth/sign-up"
                className="group mt-6 flex w-full items-center justify-center gap-1.5 rounded-full bg-primary px-5 py-3 text-sm font-semibold text-primary-foreground shadow-soft transition hover:shadow-glow"
              >
                Investor sifatida ro'yxatdan o'tish
                <ArrowUpRight className="size-4 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
              </Link>
              <p className="mt-3 text-center text-[11px] text-muted-foreground">
                Ro'yxatdan o'tgach anketangiz admin tomonidan ko'rib chiqiladi.
              </p>
            </div>
          </div>
        </div>

        {/* Related */}
        {related.length > 0 && (
          <div className="mt-20">
            <h2 className="font-display text-2xl font-semibold text-foreground">
              Boshqa loyihalar
            </h2>
            <div className="mt-6 grid grid-cols-1 gap-6 sm:grid-cols-3">
              {related.map((r) => (
                <Link
                  key={r.slug}
                  to="/invest/$slug"
                  params={{ slug: r.slug }}
                  className="group overflow-hidden rounded-2xl border border-border bg-card shadow-soft transition hover:-translate-y-1 hover:shadow-elevated"
                >
                  <div className="aspect-[16/10] overflow-hidden">
                    <img
                      src={r.image}
                      alt={r.title}
                      loading="lazy"
                      className="size-full object-cover transition-transform duration-700 group-hover:scale-[1.06]"
                    />
                  </div>
                  <div className="p-4">
                    <div className="text-xs text-muted-foreground">{r.city}</div>
                    <div className="font-display mt-1 text-sm font-semibold text-foreground">
                      {r.title}
                    </div>
                    <div className="mt-1.5 text-xs font-semibold text-success">ROI {r.roi}</div>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        )}
      </Container>
    </AppShell>
  );
}

function Stat({ icon: Icon, label, value }: { icon: typeof Wallet; label: string; value: string }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="flex items-center gap-2 text-muted-foreground">
        <Icon className="size-3.5" /> {label}
      </span>
      <span className="font-semibold text-foreground">{value}</span>
    </div>
  );
}
