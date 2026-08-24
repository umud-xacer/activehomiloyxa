/**
 * API client for the `/admin/users` panel — matches the "Users" admin operations in
 * contracts/openapi.yaml: `adminListUsers`, `adminChangeUserStatus`, `assignRole`, `revokeRole`.
 * Gated server-side by `identity:account:manage_status` (status changes) and
 * `identity:role:assign` (role grants/revokes) — this client has no client-side enforcement of
 * its own, it just calls the endpoints and surfaces the resulting 403 like any other ApiError.
 */
import { http } from "@/lib/http";

export interface UserAdminView {
  id: string;
  phoneNumber: string | null;
  email: string | null;
  status: "ACTIVE" | "SUSPENDED" | "CLOSED";
  createdAt: string | null;
  ownedProfileIds: string[] | null;
}

export interface UserAdminViewPage {
  items: UserAdminView[];
  page: { limit: number; nextCursor: string | null; total: number | null };
}

export const adminUsersApi = {
  listUsers(params: {
    status?: "ACTIVE" | "SUSPENDED" | "CLOSED";
    query?: string;
    cursor?: string;
    limit?: number;
  }): Promise<UserAdminViewPage> {
    return http.get<UserAdminViewPage>("/admin/users", { params });
  },

  changeStatus(
    userId: string,
    action: "SUSPEND" | "REACTIVATE" | "CLOSE",
    reason?: string,
  ): Promise<UserAdminView> {
    return http.post<UserAdminView>(
      `/admin/users/${userId}/status`,
      { action, ...(reason ? { reason } : {}) },
      { idempotent: true },
    );
  },

  assignRole(
    userId: string,
    roleCode: string,
    actingProfileId?: string | null,
  ): Promise<UserAdminView> {
    return http.post<UserAdminView>(
      `/admin/users/${userId}/roles`,
      { roleCode, actingProfileId: actingProfileId ?? null },
      { idempotent: true },
    );
  },

  revokeRole(
    userId: string,
    roleDefinitionHeadId: string,
    actingProfileId?: string | null,
  ): Promise<UserAdminView> {
    return http.delete<UserAdminView>(`/admin/users/${userId}/roles/${roleDefinitionHeadId}`, {
      params: actingProfileId ? { actingProfileId } : undefined,
    });
  },
};
