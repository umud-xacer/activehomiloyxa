import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Heart, MessageSquare, Bell, ArrowRight } from "lucide-react";
import { requireAuth } from "@/lib/require-auth";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { PropertyCard } from "@/components/data/PropertyCard";
import { PropertyGridSkeleton } from "@/components/data/PropertyCardSkeleton";
import { EmptyState } from "@/components/state/EmptyState";
import { favoritePropertiesOptions } from "@/features/properties/favorites-queries";
import { messagingApi } from "@/lib/messaging-api";
import { notificationsApi } from "@/lib/notifications-api";
import { formatRelativeDate } from "@/lib/format";

// No SSR `loader` -- session token only exists client-side (see favorites.tsx's own note).
export const Route = createFileRoute("/dashboard/buyer")({
  beforeLoad: requireAuth,
  head: () => ({
    meta: [
      { title: "Buyer dashboard — ActiveHome" },
      { name: "description", content: "Track searches, viewings and offers." },
    ],
  }),
  component: Page,
});

const conversationsOptions = {
  queryKey: ["conversations", "list"],
  queryFn: () => messagingApi.listConversations(),
  staleTime: 30_000,
};

const notificationsOptions = {
  queryKey: ["notifications", "list", "dashboard"],
  queryFn: () => notificationsApi.list(),
  staleTime: 30_000,
};

function Page() {
  const { data: favorites, isLoading: favoritesLoading } = useQuery(favoritePropertiesOptions(8));
  const { data: conversations = [] } = useQuery(conversationsOptions);
  const { data: notifications = [] } = useQuery(notificationsOptions);

  const unreadCount = notifications.filter((n) => !n.readAt).length;

  const kpis = [
    { label: "Saqlangan e'lonlar", value: favorites?.length ?? 0, icon: Heart, to: "/favorites" },
    { label: "Suhbatlar", value: conversations.length, icon: MessageSquare, to: "/messages" },
    { label: "O'qilmagan xabarnomalar", value: unreadCount, icon: Bell, to: "/notifications" },
  ];

  return (
    <AppShell>
      <PageHeader eyebrow="Buyer" title="Buyer dashboard" description="Track searches, viewings and offers." />
      <div className="mx-auto max-w-7xl space-y-10 px-6 py-10">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {kpis.map(({ label, value, icon: Icon, to }) => (
            <Link
              key={label}
              to={to}
              className="flex items-center justify-between rounded-2xl border border-border bg-card p-5 shadow-soft transition hover:shadow-elevated"
            >
              <div>
                <div className="text-2xl font-semibold text-foreground">{value}</div>
                <div className="text-xs text-muted-foreground">{label}</div>
              </div>
              <Icon className="size-6 text-primary" />
            </Link>
          ))}
        </div>

        <section>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-display text-lg font-semibold text-foreground">Saqlangan e'lonlar</h2>
            <Link to="/favorites" className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline">
              Barchasi <ArrowRight className="size-3.5" />
            </Link>
          </div>
          {favoritesLoading ? (
            <PropertyGridSkeleton />
          ) : favorites && favorites.length > 0 ? (
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
              {favorites.map((p, i) => (
                <PropertyCard key={p.id} property={p} index={i} />
              ))}
            </div>
          ) : (
            <EmptyState title="Hali hech narsa saqlanmagan" description="Yoqtirgan e'lonlaringizni yurak belgisi orqali saqlang." />
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
            <EmptyState title="Hali suhbatlar yo'q" description="E'lon egasiga xabar yuborsangiz, shu yerda ko'rinadi." />
          )}
        </section>
      </div>
    </AppShell>
  );
}
