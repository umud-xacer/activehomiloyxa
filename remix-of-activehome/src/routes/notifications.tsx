import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCheck, Mail, MessageSquare, Smartphone } from "lucide-react";
import { requireAuth } from "@/lib/require-auth";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/state/EmptyState";
import { notificationsApi } from "@/lib/notifications-api";
import { formatRelativeDate } from "@/lib/format";

export const Route = createFileRoute("/notifications")({
  beforeLoad: requireAuth,
  head: () => ({
    meta: [
      { title: "Notifications — ActiveHome" },
      { name: "description", content: "Everything that's happened in your account." },
    ],
  }),
  component: Page,
});

const notificationsOptions = { queryKey: ["notifications"], queryFn: () => notificationsApi.list() };

const CHANNEL_ICON = { EMAIL: Mail, WEB_PUSH: Smartphone, SMS: MessageSquare } as const;

function Page() {
  const queryClient = useQueryClient();
  const { data: notifications, isLoading } = useQuery(notificationsOptions);

  const onToggleRead = async (id: string, read: boolean) => {
    await notificationsApi.setRead(id, read);
    queryClient.invalidateQueries({ queryKey: ["notifications"] });
  };

  const onMarkAllRead = async () => {
    await notificationsApi.markAllRead();
    queryClient.invalidateQueries({ queryKey: ["notifications"] });
  };

  const unreadCount = notifications?.filter((n) => !n.readAt).length ?? 0;

  return (
    <AppShell>
      <PageHeader
        eyebrow="Activity"
        title="Notifications"
        description="Everything that's happened in your account."
        actions={
          unreadCount > 0 ? (
            <button
              onClick={onMarkAllRead}
              className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-4 py-2 text-sm font-semibold text-foreground hover:bg-muted"
            >
              <CheckCheck className="size-4" /> Hammasini o'qilgan deb belgilash
            </button>
          ) : undefined
        }
      />
      <div className="mx-auto max-w-3xl px-6 py-12">
        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-16 animate-pulse rounded-2xl bg-muted" />
            ))}
          </div>
        ) : !notifications || notifications.length === 0 ? (
          <EmptyState icon={Bell} title="Bildirishnomalar yo'q" description="Hozircha hech qanday bildirishnoma yo'q." />
        ) : (
          <div className="space-y-3">
            {notifications.map((n) => {
              const Icon = CHANNEL_ICON[n.channel];
              return (
                <button
                  key={n.id}
                  onClick={() => onToggleRead(n.id, !n.readAt)}
                  className={`flex w-full items-start gap-3 rounded-2xl border px-4 py-3 text-left transition ${
                    n.readAt ? "border-border bg-card/50" : "border-primary/30 bg-primary/5"
                  }`}
                >
                  <div className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-xl bg-card text-muted-foreground">
                    <Icon className="size-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-semibold text-foreground">{n.subject ?? n.eventKey}</div>
                    {n.body && <div className="mt-0.5 text-sm text-muted-foreground">{n.body}</div>}
                    <div className="mt-1 text-xs text-muted-foreground">{formatRelativeDate(n.createdAt)}</div>
                  </div>
                  {!n.readAt && <span className="mt-1.5 size-2 shrink-0 rounded-full bg-primary" />}
                </button>
              );
            })}
          </div>
        )}
      </div>
    </AppShell>
  );
}
