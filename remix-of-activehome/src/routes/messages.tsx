import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Send, MessageSquare, Phone } from "lucide-react";
import { requireAuth } from "@/lib/require-auth";
import { AppShell } from "@/components/layout/AppShell";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/state/EmptyState";
import { messagingApi, type Conversation } from "@/lib/messaging-api";
import { authApi } from "@/lib/auth-api";
import { formatRelativeDate } from "@/lib/format";

export const Route = createFileRoute("/messages")({
  beforeLoad: requireAuth,
  head: () => ({
    meta: [
      { title: "Messages — ActiveHome" },
      { name: "description", content: "Talk to agents, hosts and providers in one inbox." },
    ],
  }),
  component: Page,
});

const conversationsOptions = { queryKey: ["conversations"], queryFn: () => messagingApi.listConversations() };
const meOptions = { queryKey: ["me"], queryFn: () => authApi.getMe() };

function ConversationThread({ conversation, myUserId }: { conversation: Conversation; myUserId?: string }) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState("");
  const [phone, setPhone] = useState<{ allowed: boolean; phoneNumber: string | null } | null>(null);
  const [revealing, setRevealing] = useState(false);
  const { data: messages } = useQuery({
    queryKey: ["messages", conversation.id],
    queryFn: () => messagingApi.listMessages(conversation.id),
    refetchInterval: 5000,
  });

  const onSend = async () => {
    if (!draft.trim()) return;
    await messagingApi.sendMessage(conversation.id, draft.trim());
    setDraft("");
    queryClient.invalidateQueries({ queryKey: ["messages", conversation.id] });
    queryClient.invalidateQueries({ queryKey: ["conversations"] });
  };

  const onRevealPhone = async () => {
    setRevealing(true);
    try {
      setPhone(await messagingApi.revealPhone(conversation.id));
    } finally {
      setRevealing(false);
    }
  };

  return (
    <div className="flex h-[520px] flex-col">
      <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
        <span className="text-sm font-semibold text-foreground">Suhbat #{conversation.id.slice(0, 8)}</span>
        {phone ? (
          <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-foreground">
            <Phone className="size-3.5 text-primary" />
            {phone.allowed && phone.phoneNumber ? phone.phoneNumber : "Raqam mavjud emas / ruxsat berilmagan"}
          </span>
        ) : (
          <button
            onClick={onRevealPhone}
            disabled={revealing}
            className="inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-1 text-xs font-semibold text-foreground hover:bg-muted disabled:opacity-50"
          >
            <Phone className="size-3.5" /> Telefon raqamni ko'rsatish
          </button>
        )}
      </div>
      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {messages?.length ? (
          messages.map((m) => {
            const mine = m.authorUserId === myUserId;
            return (
              <div key={m.id} className={`flex ${mine ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[75%] rounded-2xl px-4 py-2 text-sm ${
                    mine ? "bg-primary text-primary-foreground" : "bg-muted text-foreground"
                  }`}
                >
                  {m.body}
                  <div className={`mt-1 text-[10px] ${mine ? "text-primary-foreground/70" : "text-muted-foreground"}`}>
                    {formatRelativeDate(m.sentAt)}
                  </div>
                </div>
              </div>
            );
          })
        ) : (
          <p className="text-center text-sm text-muted-foreground">Hozircha xabar yo'q.</p>
        )}
      </div>
      <div className="flex items-center gap-2 border-t border-border p-3">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onSend()}
          placeholder="Xabar yozing..."
          className="flex-1 rounded-full border border-border bg-background px-4 py-2 text-sm text-foreground"
        />
        <button
          onClick={onSend}
          className="inline-flex size-9 items-center justify-center rounded-full bg-primary text-primary-foreground hover:shadow-glow"
        >
          <Send className="size-4" />
        </button>
      </div>
    </div>
  );
}

function Page() {
  const { data: conversations, isLoading } = useQuery(conversationsOptions);
  const { data: me } = useQuery(meOptions);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = conversations?.find((c) => c.id === selectedId) ?? conversations?.[0];

  return (
    <AppShell>
      <PageHeader eyebrow="Inbox" title="Messages" description="Talk to agents, hosts and providers in one inbox." />
      <div className="mx-auto max-w-5xl px-6 py-12">
        {isLoading ? (
          <div className="h-96 animate-pulse rounded-2xl bg-muted" />
        ) : !conversations || conversations.length === 0 ? (
          <EmptyState
            icon={MessageSquare}
            title="Xabarlar yo'q"
            description="E'lon egasiga xabar yozganingizda, suhbat shu yerda paydo bo'ladi."
          />
        ) : (
          <div className="grid grid-cols-1 overflow-hidden rounded-3xl border border-border bg-card shadow-soft md:grid-cols-[280px_1fr]">
            <div className="max-h-[520px] overflow-y-auto border-b border-border md:border-b-0 md:border-r">
              {conversations.map((c) => (
                <button
                  key={c.id}
                  onClick={() => setSelectedId(c.id)}
                  className={`block w-full border-b border-border/60 px-4 py-3 text-left transition hover:bg-muted ${
                    selected?.id === c.id ? "bg-muted" : ""
                  }`}
                >
                  <div className="text-sm font-semibold text-foreground">Suhbat #{c.id.slice(0, 8)}</div>
                  <div className="text-xs text-muted-foreground">
                    {c.lastMessageAt ? formatRelativeDate(c.lastMessageAt) : formatRelativeDate(c.createdAt)}
                  </div>
                </button>
              ))}
            </div>
            {selected && <ConversationThread conversation={selected} myUserId={me?.id} />}
          </div>
        )}
      </div>
    </AppShell>
  );
}
