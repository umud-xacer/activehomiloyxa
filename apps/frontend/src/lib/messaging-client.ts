/**
 * Messaging API client — matches contracts/openapi.yaml's conversation/message paths
 * (`/conversations`, `/conversations/{id}/messages`, `/conversations/{id}/phone-reveal`).
 */
import { http } from "@/lib/http";

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
