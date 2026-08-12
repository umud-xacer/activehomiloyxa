/**
 * Messaging API client — matches contracts/openapi.yaml's conversation/message paths
 * (`/conversations`, `/conversations/{id}/messages`, `/conversations/{id}/phone-reveal`).
 */
import { http, ApiError } from "@/lib/http";

export interface Conversation {
  id: string;
  listingId: string;
  initiatorUserId: string;
  recipientUserId: string;
  status: "INITIATED" | "ACTIVE" | "ARCHIVED";
  lastMessageAt: string | null;
  createdAt: string;
}

export interface Message {
  id: string;
  conversationId: string;
  authorUserId: string;
  body: string;
  sentAt: string;
  deliveredAt: string | null;
  readAt: string | null;
}

interface Page<T> {
  items: T[];
  page: { limit: number; nextCursor: string | null; total: number | null };
}

export const messagingApi = {
  listConversations(cursor?: string, limit = 40): Promise<Page<Conversation>> {
    return http.get<Page<Conversation>>("/conversations", { params: { cursor, limit } });
  },
  startConversation(listingId: string, message: string): Promise<Conversation> {
    return http.post<Conversation>("/conversations", { listingId, message }, { idempotent: true });
  },
  getConversation(conversationId: string): Promise<Conversation> {
    return http.get<Conversation>(`/conversations/${conversationId}`);
  },
  listMessages(conversationId: string, cursor?: string, limit = 60): Promise<Page<Message>> {
    return http.get<Page<Message>>(`/conversations/${conversationId}/messages`, {
      params: { cursor, limit },
    });
  },
  sendMessage(conversationId: string, body: string): Promise<Message> {
    return http.post<Message>(
      `/conversations/${conversationId}/messages`,
      { body },
      { idempotent: true },
    );
  },
  revealPhone(conversationId: string): Promise<{ allowed: boolean; phoneNumber: string | null }> {
    return http.post(`/conversations/${conversationId}/phone-reveal`);
  },
};

/**
 * `startConversation` is one-per-(listing, initiator) on the backend (409 `DUPLICATE_KEY` on a
 * repeat call) -- the Problem envelope never carries the existing conversation's id back inline,
 * so on a 409 the only way to recover it is to list and match by `listingId`. Without this, a
 * caller who already has a conversation for a listing (came back, or double-clicked) gets a raw
 * "conversation already exists" error instead of being taken to their existing thread.
 */
export async function ensureConversationForListing(
  listingId: string,
  message: string,
): Promise<Conversation> {
  try {
    return await messagingApi.startConversation(listingId, message);
  } catch (err) {
    if (err instanceof ApiError && err.status === 409) {
      const { items } = await messagingApi.listConversations();
      const existing = items.find((c) => c.listingId === listingId);
      if (existing) return existing;
    }
    throw err;
  }
}
