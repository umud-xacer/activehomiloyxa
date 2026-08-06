import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, BellOff, Loader2, CheckCheck } from "lucide-react";
import { requireAuth } from "@/lib/require-auth";
import { DashboardShell } from "@/components/layout/DashboardShell";
import { SectionCard } from "@/components/dashboard/SectionCard";
import { EmptyState } from "@/components/dashboard/EmptyState";
import { useMe } from "@/features/auth/useAuth";
import { notificationsApi } from "@/lib/notifications-client";

export const Route = createFileRoute("/notifications")({
  beforeLoad: requireAuth,
  head: () => ({
    meta: [
      { title: "Bildirishnomalar — ActiveHome" },
      { name: "description", content: "Tizim bildirishnomalari ro'yxati." },
    ],
  }),
  component: Page,
});

function Page() {
  const { data: account } = useMe();
  const queryClient = useQueryClient();

  const { data: notifications = [], isLoading } = useQuery({
    queryKey: ["notifications"],
    queryFn: async () => (await notificationsApi.list()).items,
  });

  const unreadCount = notifications.filter((n) => !n.readAt).length;

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["notifications"] });

  const toggleRead = async (id: string, read: boolean) => {
    await notificationsApi.setRead(id, read);
    invalidate();
  };

  const markAllRead = async () => {
    await notificationsApi.markAllRead();
    invalidate();
  };

  return (
    <DashboardShell account={account}>
      <div className="mx-auto max-w-5xl space-y-6 px-4 py-8 lg:px-8">
        <SectionCard
          title="Bildirishnomalar"
          icon={Bell}
          description={unreadCount > 0 ? `${unreadCount} ta o'qilmagan` : undefined}
          noPadding={notifications.length > 0}
          action={
            unreadCount > 0 ? (
              <button
                type="button"
                onClick={markAllRead}
                className="inline-flex items-center gap-1.5 text-sm font-semibold text-primary hover:underline"
              >
                <CheckCheck className="size-3.5" /> Barchasini o'qilgan deb belgilash
              </button>
            ) : undefined
          }
        >
          {isLoading ? (
            <div className="flex items-center gap-2 p-6 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" /> Yuklanmoqda…
            </div>
          ) : notifications.length === 0 ? (
            <EmptyState
              icon={BellOff}
              title="Hozircha bildirishnoma yo'q"
              description="Yangi bildirishnomalar shu yerda ko'rinadi."
            />
          ) : (
            <ul className="divide-y divide-border">
              {notifications.map((n) => (
                <li
                  key={n.id}
                  className={`flex items-start justify-between gap-4 px-6 py-4 ${
                    !n.readAt ? "bg-primary/5" : ""
                  }`}
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      {!n.readAt && <span className="size-1.5 shrink-0 rounded-full bg-primary" />}
                      <div className="truncate font-medium text-foreground">
                        {n.subject || n.eventKey}
                      </div>
                    </div>
                    <p className="mt-1 text-sm text-muted-foreground">{n.body}</p>
                    <div className="mt-1 text-[11px] text-muted-foreground">
                      {new Date(n.createdAt).toLocaleString()}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => toggleRead(n.id, !n.readAt)}
                    className="shrink-0 text-xs font-semibold text-primary hover:underline"
                  >
                    {n.readAt ? "O'qilmagan deb belgilash" : "O'qilgan deb belgilash"}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      </div>
    </DashboardShell>
  );
}
