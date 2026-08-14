import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  Building2,
  ShieldCheck,
  ShieldAlert,
  Loader2,
  Plus,
  MessageSquare,
  CreditCard,
  Eye,
  Package,
  TrendingUp,
  ArrowUpRight,
} from "lucide-react";
import { requireOnboardedLegalEntity } from "@/lib/require-auth";
import { DashboardShell } from "@/components/layout/DashboardShell";
import { Container } from "@/components/layout/Container";
import { ReviewGate } from "@/components/auth/ReviewGate";
import { SubscriptionGate } from "@/components/auth/SubscriptionGate";
import { StatCard } from "@/components/dashboard/StatCard";
import { SectionCard } from "@/components/dashboard/SectionCard";
import { ListingsTable } from "@/components/dashboard/ListingsTable";
import { businessProfilesApi, type BusinessProfile } from "@/lib/business-profiles-client";
import { catalogClient } from "@/lib/catalog-client";
import { useMe } from "@/features/auth/useAuth";

export const Route = createFileRoute("/dashboard/seller")({
  beforeLoad: requireOnboardedLegalEntity,
  head: () => ({
    meta: [
      { title: "Yuridik shaxs paneli — ActiveHome" },
      { name: "description", content: "Biznes profilingiz, e'lonlaringiz va tasdiqlash holati." },
    ],
  }),
  component: Page,
});

function useOwnedProfiles(ownedProfileIds: string[]) {
  return useQuery({
    queryKey: ["business-profiles", "mine", ownedProfileIds],
    queryFn: () => Promise.all(ownedProfileIds.map((id) => businessProfilesApi.get(id))),
    enabled: ownedProfileIds.length > 0,
  });
}

function profileName(p: BusinessProfile): string {
  return p.name.uz_latn || p.name.en || p.name.ru || "—";
}

function VerificationRow({ profile }: { profile: BusinessProfile }) {
  const { data: verification } = useQuery({
    queryKey: ["verification", profile.id],
    queryFn: () => businessProfilesApi.getVerification(profile.id),
  });
  const badge = profile.badge?.status;
  const verified = badge === "VALID";

  return (
    <SectionCard
      title="Biznes profili"
      icon={Building2}
      index={1}
      action={
        <Link
          to="/dashboard/business-profile"
          className="text-sm font-semibold text-primary hover:underline"
        >
          Tahrirlash
        </Link>
      }
    >
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="flex size-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
            <Building2 className="size-5" />
          </div>
          <div>
            <div className="font-display text-base font-semibold text-foreground">
              {profileName(profile)}
            </div>
            <div className="text-xs text-muted-foreground">{profile.profileType}</div>
          </div>
        </div>
        <div
          className={`inline-flex items-center gap-2 rounded-2xl px-4 py-2 text-sm font-semibold ${
            verified ? "bg-success/10 text-success" : "bg-amber-500/10 text-amber-600"
          }`}
        >
          {verified ? <ShieldCheck className="size-4" /> : <ShieldAlert className="size-4" />}
          {verified ? "Tasdiqlangan" : verification ? verification.status : "Tasdiqlanmagan"}
        </div>
      </div>
      {!verified && (
        <div className="mt-4 rounded-xl border border-dashed border-border bg-background/50 px-4 py-3 text-xs text-muted-foreground">
          Ishonch nishonini olish uchun{" "}
          <Link to="/verification" className="font-semibold text-primary hover:underline">
            tasdiqlashni so'rang
          </Link>
          .
        </div>
      )}
    </SectionCard>
  );
}

function Page() {
  const { data: account } = useMe();
  if (!account) return null;

  return (
    <DashboardShell account={account}>
      <ReviewGate account={account}>
        <SubscriptionGate account={account}>
          <SellerContent account={account} />
        </SubscriptionGate>
      </ReviewGate>
    </DashboardShell>
  );
}

function SellerContent({ account }: { account: NonNullable<ReturnType<typeof useMe>["data"]> }) {
  const ownedProfileIds = account.ownedProfileIds ?? [];
  const { data: profiles, isLoading: profilesLoading } = useOwnedProfiles(ownedProfileIds);
  const { data: listings = [], isLoading: listingsLoading } = useQuery({
    queryKey: ["catalog", "my-listings"],
    queryFn: () => catalogClient.myListings(50),
  });

  const activeCount = listings.filter(
    (l) => l.lifecycleState === "PUBLISHED" || l.lifecycleState === "EDITED",
  ).length;
  const primaryProfile = profiles?.[0];

  return (
    <Container wide className="space-y-8 py-8">
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
        className="relative overflow-hidden rounded-3xl border border-border bg-card p-8 shadow-soft"
      >
        <div className="gradient-mesh absolute inset-0 -z-10 opacity-70" />
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="font-display text-3xl font-semibold tracking-tight">
              Xush kelibsiz, {account.displayName || "Hamkor"}
            </h1>
            <p className="mt-2 max-w-xl text-sm text-muted-foreground">
              Yuridik shaxs — ishlab chiqaruvchi paneli. Biznesingiz holati bir qarashda shu yerda.
            </p>
          </div>
          <Link
            to="/list"
            className="inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground shadow-soft transition hover:shadow-glow"
          >
            <Plus className="size-4" /> Yangi e'lon
          </Link>
        </div>
      </motion.div>

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          icon={Package}
          label="Faol e'lonlar"
          value={activeCount}
          accent="primary"
          index={0}
        />
        <StatCard icon={Eye} label="Bu hafta ko'rishlar" value={0} accent="info" index={1} />
        <StatCard
          icon={MessageSquare}
          label="Yangi murojaatlar"
          value={0}
          accent="success"
          index={2}
        />
        <StatCard
          icon={TrendingUp}
          label="Tasdiqlash holati"
          value={primaryProfile?.badge?.status === "VALID" ? "Ha" : "Yo'q"}
          accent="warning"
          index={3}
        />
      </section>

      {profilesLoading || !primaryProfile ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Yuklanmoqda…
        </div>
      ) : (
        <VerificationRow profile={primaryProfile} />
      )}

      <SectionCard
        title="Mening e'lonlarim"
        icon={Package}
        noPadding={listings.length > 0}
        index={2}
        action={
          <Link to="/list" className="text-sm font-semibold text-primary hover:underline">
            + Yangi
          </Link>
        }
      >
        {listingsLoading ? (
          <div className="flex items-center gap-2 p-6 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Yuklanmoqda…
          </div>
        ) : (
          <ListingsTable listings={listings} />
        )}
      </SectionCard>

      <div className="grid gap-4 sm:grid-cols-2">
        <Link
          to="/messages"
          className="group flex items-center gap-3 rounded-2xl border border-border bg-card p-5 shadow-soft transition hover:-translate-y-0.5 hover:shadow-elevated"
        >
          <MessageSquare className="size-5 text-primary" />
          <div className="flex-1">
            <div className="text-sm font-semibold text-foreground">Xabarlar</div>
            <div className="text-xs text-muted-foreground">Mijozlar bilan muloqot</div>
          </div>
          <ArrowUpRight className="size-4 text-foreground/30 transition group-hover:text-primary" />
        </Link>
        <Link
          to="/subscriptions"
          className="group flex items-center gap-3 rounded-2xl border border-border bg-card p-5 shadow-soft transition hover:-translate-y-0.5 hover:shadow-elevated"
        >
          <CreditCard className="size-5 text-primary" />
          <div className="flex-1">
            <div className="text-sm font-semibold text-foreground">Obunalar</div>
            <div className="text-xs text-muted-foreground">Reklama va targ'ibot rejalari</div>
          </div>
          <ArrowUpRight className="size-4 text-foreground/30 transition group-hover:text-primary" />
        </Link>
      </div>
    </Container>
  );
}
