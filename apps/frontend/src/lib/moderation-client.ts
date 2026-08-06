/**
 * API client for the `/admin/moderation` panel — matches the moderation-tagged operations in
 * contracts/openapi.yaml: `listModerationQueue`, `getModerationCase`, `applyModerationAction`.
 * Gated server-side via `get_acting_moderator` (moderation module's own permission check).
 */
import { http } from "@/lib/http";

export type ModerationSubjectType = "LISTING" | "CONVERSATION" | "USER" | "PROFILE";
export type ModerationCaseStatus = "OPEN" | "IN_REVIEW" | "RESOLVED";
export type ModerationAction =
  | "HIDE"
  | "REJECT"
  | "SUSPEND"
  | "REQUEST_CORRECTION"
  | "REMOVE"
  | "SUSPEND_ACCOUNT"
  | "DISMISS"
  | "REVOKE_BADGE"
  | "ARCHIVE_PROFILE";

/** Which actions are legal for which subject type (mirrors backend's `ACTIONS_BY_SUBJECT_TYPE` —
 * applying a mismatched verb is a caller bug there, so we only ever offer the legal subset here). */
export const ACTIONS_BY_SUBJECT_TYPE: Record<ModerationSubjectType, ModerationAction[]> = {
  LISTING: ["HIDE", "REJECT", "SUSPEND", "REQUEST_CORRECTION", "REMOVE", "DISMISS"],
  USER: ["SUSPEND_ACCOUNT", "REQUEST_CORRECTION", "DISMISS"],
  PROFILE: ["REVOKE_BADGE", "ARCHIVE_PROFILE", "REQUEST_CORRECTION", "DISMISS"],
  CONVERSATION: ["SUSPEND_ACCOUNT", "REQUEST_CORRECTION", "DISMISS"],
};

export interface ModerationCase {
  id: string;
  subjectType: ModerationSubjectType;
  subjectId: string;
  originType: "USER_REPORT" | "AUTOMATED_FLAG";
  reportReason: string | null;
  ruleKey: string | null;
  status: ModerationCaseStatus;
  resolutionAction: ModerationAction | null;
  createdAt: string;
}

export interface ModerationCasePage {
  items: ModerationCase[];
  page: { limit: number; nextCursor: string | null; total: number | null };
}

export const moderationApi = {
  listQueue(params: {
    status?: ModerationCaseStatus;
    subjectType?: ModerationSubjectType;
    cursor?: string;
    limit?: number;
  }): Promise<ModerationCasePage> {
    return http.get<ModerationCasePage>("/admin/moderation-queue", { params });
  },

  getCase(caseId: string): Promise<ModerationCase> {
    return http.get<ModerationCase>(`/admin/moderation-queue/${caseId}`);
  },

  applyAction(caseId: string, action: ModerationAction, note?: string): Promise<ModerationCase> {
    return http.post<ModerationCase>(
      `/admin/moderation-queue/${caseId}/action`,
      { action, ...(note ? { note } : {}) },
      { idempotent: true },
    );
  },
};
