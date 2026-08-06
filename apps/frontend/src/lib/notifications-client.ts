/**
 * Notifications API client — matches the "Notifications" section of contracts/openapi.yaml
 * (`GET /me/notifications`, `POST /me/notifications/{id}/read`, `POST /me/notifications/read-all`).
 */
import { http } from "@/lib/http";

export interface Notification {
  id: string;
  eventKey: string;
  channel: "EMAIL" | "WEB_PUSH" | "SMS";
  subject: string | null;
  body: string;
  readAt: string | null;
  deliveryStatus: "QUEUED" | "SENT" | "DELIVERED" | "FAILED";
  createdAt: string;
}

interface NotificationPage {
  items: Notification[];
  page: { limit: number; nextCursor: string | null; total: number | null };
}

export const notificationsApi = {
  list(cursor?: string, limit = 40): Promise<NotificationPage> {
    return http.get<NotificationPage>("/me/notifications", { params: { cursor, limit } });
  },
  setRead(notificationId: string, read: boolean): Promise<Notification> {
    return http.post<Notification>(`/me/notifications/${notificationId}/read`, { read });
  },
  markAllRead(): Promise<void> {
    return http.post<void>("/me/notifications/read-all");
  },
};
