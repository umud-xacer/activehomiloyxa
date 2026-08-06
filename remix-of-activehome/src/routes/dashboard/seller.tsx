import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Building2, Heart, MessageSquare, Plus, ShieldCheck, ArrowRight } from "lucide-react";
import { requireAuth } from "@/lib/require-auth";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/state/EmptyState";
import { listingApi, type BackendListing, type ListingStatistics } from "@/lib/listing-api";
import { authApi } from "@/lib/auth-api";
import { profilesApi } from "@/lib/profiles-api";
import { verificationApi, type VerificationCase } from "@/lib/verification-api";
import { messagingApi } from "@/lib/messaging-api";
import { formatPriceWithUnit, formatRelativeDate } from "@/lib/format";
import { ApiError } from "@/lib/http";

// No SSR `loader` -- session token only exists client-side (see favorites.tsx's own note).
export const Route = createFileRoute("/dashboard/seller")({
  beforeLoad: requireAuth,
  head: () => ({
    meta: [
      { title: "Seller dashboard — ActiveHome" },
      { name: "description", content: "Manage your listings, leads and analytics." },
    ],
  }),
  component: Page,
});

const LIFECYCLE_LABEL: Record<BackendListing["lifecycleState"], string> = {
  DRAFT: "Qoralama",
  PENDING_VERIFICATION: "Tekshiruvda",
  PUBLISHED: "Nashr qilingan",
  EDITED: "Tahrirlangan",
  SUSPENDED: "To'xtatilgan",
  ARCHIVED: "Arxivlangan",
  DELETED: "O'chirilgan",
};

const myListingsOptions = {
  queryKey: ["listings", "mine"],
  queryFn: () => listingApi.listMyListings(),
  staleTime: 30_000,
};

const listingStatsOptions = (listings: BackendListing[] | undefined) => ({
  queryKey: ["listings", "mine", "statistics", listings?.map((l) => l.id)],
  queryFn: async (): Promise<Record<string, ListingStatistics>> => {
    const entries = await Promise.all(
      (listings ?? []).map(async (l) => [l.id, await listingApi.getListingStatistics(l.id)] as const),
    );
    return Object.fromEntries(entries);
  },
  enabled: !!listings && listings.length > 0,
  staleTime: 30_000,
});

// `GET /business-profiles` is a public directory (every profile, not just the caller's own) --
// the account's OWN profile ids live on `GET /me`'s `ownedProfileIds` instead (identity module's
// `UserAccount.owned_profile_ids`, projected from `profiles.BusinessProfileCreated`).
const myBusinessProfilesOptions = {
  queryKey: ["business-profiles", "mine"],
  queryFn: async () => {
    const me = await authApi.getMe();
    const ids = me.ownedProfileIds ?? [];
    return Promise.all(ids.map((id) => profilesApi.getBusinessProfile(id)));
  },
  staleTime: 60_000,
};

const verificationOptions = (profileId: string | undefined) => ({
  queryKey: ["verification", profileId],
  queryFn: async (): Promise<VerificationCase | null> => {
    if (!profileId) return null;
    try {
      return await verificationApi.getCase(profileId);
    } catch (err) {
      if (err instanceof ApiError && err.problem.status === 404) return null;
      throw err;
    }
  },
  enabled: !!profileId,
  staleTime: 30_000,
});

const conversationsOptions = {
  queryKey: ["conversations", "list"],
  queryFn: () => messagingApi.listConversations(),
  staleTime: 30_000,
};

function Page() {
  const { data: listings = [], isLoading: listingsLoading } = useQuery(myListingsOptions);
  const { data: stats = {} } = useQuery(listingStatsOptions(listings));
  const { data: profiles = [] } = useQuery(myBusinessProfilesOptions);
  const { data: verification } = useQuery(verificationOptions(profiles[0]?.id));
  const { data: conversations = [] } = useQuery(conversationsOptions);

  const published = listings.filter((l) => l.lifecycleState === "PUBLISHED" || l.lifecycleState === "EDITED");
  const totalFavorites = Object.values(stats).reduce((sum, s) => sum + (s.favorites ?? 0), 0);

  const kpis = [
    { label: "Jami e'lonlar", value: listings.length, icon: Building2 },
    { label: "Nashr qilingan", value: published.length, icon: ArrowRight },
    { label: "Saqlanganlar (barcha e'lonlar bo'yicha)", value: totalFavorites, icon: Heart },
    { label: "Suhbatlar", value: conversations.length, icon: MessageSquare },
  ];

  return (
    <AppShell>
      <PageHeader
        eyebrow="Seller"
        title="Seller dashboard"
        description="Manage your listings, leads and analytics."
        actions={
          <Link
            to="/list"
            className="inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:shadow-glow"
          >
            <Plus className="size-4" /> Yangi e'lon
          </Link>
        }
      />
      <div className="mx-auto max-w-7xl space-y-10 px-6 py-10">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {kpis.map(({ label, value, icon: Icon }) => (
            <div key={label} className="flex items-center justify-between rounded-2xl border border-border bg-card p-5 shadow-soft">
              <div>
                <div className="text-2xl font-semibold text-foreground">{value}</div>
                <div className="text-xs text-muted-foreground">{label}</div>
              </div>
              <Icon className="size-6 text-primary" />
            </div>
          ))}
        </div>

        {profiles.length > 0 && (
          <section className="rounded-2xl border border-border bg-card p-5 shadow-soft">
            <div className="flex items-center gap-3">
              <ShieldCheck className={`size-5 ${verification?.status === "APPROVED" ? "text-success" : "text-muted-foreground"}`} />
              <div className="text-sm">
                <div className="font-semibold text-foreground">
                  {profiles[0].name.uz_latn ?? "Biznes profil"}
                </div>
                <div className="text-xs text-muted-foreground">
                  {verification === null && "Tasdiqlash so'ralmagan"}
                  {verification?.status === "REQUESTED" && "Tasdiqlash so'rovi yuborilgan — ko'rib chiqilmoqda"}
                  {verification?.status === "IN_REVIEW" && "Tekshiruvda"}
                  {verification?.status === "APPROVED" && "Tasdiqlangan biznes"}
                  {verification?.status === "REJECTED" && "Tasdiqlash rad etilgan"}
                </div>
              </div>
              <Link
                to="/business-profile/$id"
                params={{ id: profiles[0].id }}
                className="ml-auto inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline"
              >
                Profilni boshqarish <ArrowRight className="size-3.5" />
              </Link>
            </div>
          </section>
        )}

        <section>
          <h2 className="mb-4 font-display text-lg font-semibold text-foreground">Mening e'lonlarim</h2>
          {listingsLoading ? (
            <div className="h-40 animate-pulse rounded-2xl bg-muted" />
          ) : listings.length > 0 ? (
            <div className="divide-y divide-border rounded-2xl border border-border bg-card">
              {listings.map((l) => (
                <div key={l.id} className="flex items-center justify-between gap-4 px-5 py-4 text-sm hover:bg-muted/50">
                  <Link to="/properties/$slug" params={{ slug: l.slug }} className="min-w-0 flex-1">
                    <div className="truncate font-medium text-foreground">{l.title}</div>
                    <div className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
                      <span className="rounded-full bg-muted px-2 py-0.5 font-semibold">
                        {LIFECYCLE_LABEL[l.lifecycleState]}
                      </span>
                      {l.price && <span>{formatPriceWithUnit(Number(l.price.amount), l.price.currency as never, "sale")}</span>}
                    </div>
                  </Link>
                  <div className="flex shrink-0 items-center gap-4 text-xs text-muted-foreground">
                    <span className="inline-flex items-center gap-1">
                      <Heart className="size-3.5" /> {stats[l.id]?.favorites ?? 0}
                    </span>
                    <span>{formatRelativeDate(l.createdAt)}</span>
                    <Link
                      to="/listings/$id/edit"
                      params={{ id: l.id }}
                      className="rounded-full border border-border px-2.5 py-1 font-semibold text-foreground hover:bg-muted"
                    >
                      Tahrirlash
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              icon={Building2}
              title="Hali e'lonlaringiz yo'q"
              description="Birinchi e'loningizni joylashtiring."
              action={
                <Link to="/list" className="inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:shadow-glow">
                  <Plus className="size-4" /> E'lon joylash
                </Link>
              }
            />
          )}
        </section>

        <section>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-display text-lg font-semibold text-foreground">So'nggi suhbatlar</h2>
            <Link to="/messages" className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline">
              Barchasi <ArrowRight className="size-3.5" />
            </Link>
          </div>
          {conversations.length > 0 ? (
            <div className="divide-y divide-border rounded-2xl border border-border bg-card">
              {conversations.slice(0, 5).map((c) => (
                <div key={c.id} className="flex items-center justify-between px-5 py-3.5 text-sm">
                  <div className="flex items-center gap-2 text-foreground">
                    <MessageSquare className="size-4 text-muted-foreground" />
                    <span className="font-medium">Suhbat #{c.id.slice(0, 8)}</span>
                    <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-semibold uppercase text-muted-foreground">
                      {c.status}
                    </span>
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {c.lastMessageAt ? formatRelativeDate(c.lastMessageAt) : formatRelativeDate(c.createdAt)}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState title="Hali suhbatlar yo'q" description="Xaridorlar sizga xabar yozganda shu yerda ko'rinadi." />
          )}
        </section>
      </div>
    </AppShell>
  );
}
