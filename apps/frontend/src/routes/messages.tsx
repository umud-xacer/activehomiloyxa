import { createFileRoute } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { MessageSquare, Send, Loader2, Phone } from "lucide-react";
import { requireAuth } from "@/lib/require-auth";
import { DashboardShell } from "@/components/layout/DashboardShell";
import { EmptyState } from "@/components/dashboard/EmptyState";
import { useMe } from "@/features/auth/useAuth";
import { messagingApi, type Conversation } from "@/lib/messaging-client";
import { catalogClient } from "@/lib/catalog-client";
import { ApiError } from "@/lib/http";

export const Route = createFileRoute("/messages")({
  beforeLoad: requireAuth,
  head: () => ({
    meta: [
      { title: "Xabarlar — ActiveHome" },
      { name: "description", content: "Sotuvchilar va xaridorlar bilan yozishmalar." },
    ],
  }),
  component: Page,
});

function Page() {
  const { data: account } = useMe();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { data: conversations = [], isLoading } = useQuery({
    queryKey: ["conversations"],
    queryFn: async () => (await messagingApi.listConversations()).items,
    refetchInterval: 15_000,
  });

  return (
    <DashboardShell account={account}>
      <div className="mx-auto flex h-[calc(100vh-4rem)] max-w-6xl">
        <aside className="flex w-full max-w-xs shrink-0 flex-col border-r border-border">
          <div className="border-b border-border px-5 py-4">
            <h1 className="font-display text-lg font-semibold text-foreground">Xabarlar</h1>
          </div>
          <div className="flex-1 overflow-y-auto">
            {isLoading ? (
              <div className="flex items-center gap-2 p-5 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" /> Yuklanmoqda…
              </div>
            ) : conversations.length === 0 ? (
              <div className="p-5">
                <EmptyState icon={MessageSquare} title="Hali suhbat yo'q" compact />
              </div>
            ) : (
              <ul>
                {conversations.map((c) => (
                  <ConversationRow
                    key={c.id}
                    conversation={c}
                    active={c.id === selectedId}
                    onClick={() => setSelectedId(c.id)}
                  />
                ))}
              </ul>
            )}
          </div>
        </aside>

        <section className="flex-1">
          {selectedId ? (
            <Thread key={selectedId} conversationId={selectedId} myUserId={account?.id ?? null} />
          ) : (
            <div className="flex h-full items-center justify-center">
              <EmptyState
                icon={MessageSquare}
                title="Suhbatni tanlang"
                description="Chapdan bir suhbatni bosing."
              />
            </div>
          )}
        </section>
      </div>
    </DashboardShell>
  );
}

function ConversationRow({
  conversation,
  active,
  onClick,
}: {
  conversation: Conversation;
  active: boolean;
  onClick: () => void;
}) {
  const { data: listing } = useQuery({
    queryKey: ["catalog", "listing", conversation.listingId],
    queryFn: () => catalogClient.getListing(conversation.listingId),
    staleTime: 5 * 60_000,
  });

  return (
    <li>
      <button
        type="button"
        onClick={onClick}
        className={`flex w-full flex-col items-start gap-0.5 border-b border-border/60 px-5 py-3 text-left transition ${
          active ? "bg-primary/5" : "hover:bg-muted/50"
        }`}
      >
        <span className="truncate text-sm font-medium text-foreground">
          {listing?.title ?? "E'lon"}
        </span>
        <span className="text-xs text-muted-foreground">
          {conversation.lastMessageAt
            ? new Date(conversation.lastMessageAt).toLocaleString()
            : new Date(conversation.createdAt).toLocaleString()}
        </span>
      </button>
    </li>
  );
}

function Thread({ conversationId, myUserId }: { conversationId: string; myUserId: string | null }) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [phone, setPhone] = useState<{ allowed: boolean; phoneNumber: string | null } | null>(null);
  const [revealing, setRevealing] = useState(false);

  const { data: messages = [], isLoading } = useQuery({
    queryKey: ["conversation-messages", conversationId],
    queryFn: async () => (await messagingApi.listMessages(conversationId)).items,
    refetchInterval: 8_000,
  });

  const send = async (e: FormEvent) => {
    e.preventDefault();
    const body = draft.trim();
    if (!body) return;
    setSending(true);
    setError(null);
    try {
      await messagingApi.sendMessage(conversationId, body);
      setDraft("");
      queryClient.invalidateQueries({ queryKey: ["conversation-messages", conversationId] });
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Yuborilmadi.");
    } finally {
      setSending(false);
    }
  };

  const revealPhone = async () => {
    setRevealing(true);
    try {
      setPhone(await messagingApi.revealPhone(conversationId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Ko'rsatib bo'lmadi.");
    } finally {
      setRevealing(false);
    }
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-border px-5 py-4">
        <span className="text-sm font-medium text-foreground">Suhbat</span>
        <button
          type="button"
          onClick={revealPhone}
          disabled={revealing}
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-primary hover:underline disabled:opacity-60"
        >
          <Phone className="size-3.5" />
          {phone ? (phone.allowed ? phone.phoneNumber : "Ko'rsatilmaydi") : "Telefonni ko'rsatish"}
        </button>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto px-5 py-4">
        {isLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Yuklanmoqda…
          </div>
        ) : (
          messages.map((m) => {
            const mine = m.authorUserId === myUserId;
            return (
              <div key={m.id} className={`flex ${mine ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[70%] rounded-2xl px-4 py-2.5 text-sm ${
                    mine
                      ? "bg-primary text-primary-foreground"
                      : "border border-border bg-card text-foreground"
                  }`}
                >
                  <p className="whitespace-pre-wrap">{m.body}</p>
                  <p
                    className={`mt-1 text-[10px] ${mine ? "text-primary-foreground/70" : "text-muted-foreground"}`}
                  >
                    {new Date(m.sentAt).toLocaleTimeString()}
                  </p>
                </div>
              </div>
            );
          })
        )}
      </div>

      <form onSubmit={send} className="flex items-center gap-2 border-t border-border px-5 py-4">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Xabar yozing…"
          className="flex-1 rounded-full border border-border bg-background px-4 py-2.5 text-sm text-foreground outline-none focus:ring-2 focus:ring-primary/30"
        />
        <button
          type="submit"
          disabled={sending || !draft.trim()}
          className="flex size-10 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-soft hover:shadow-glow disabled:opacity-60"
        >
          {sending ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
        </button>
      </form>
      {error && <p className="px-5 pb-3 text-xs text-destructive">{error}</p>}
    </div>
  );
}
