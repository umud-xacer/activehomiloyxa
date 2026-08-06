/**
 * Identity API client — matches the "Authentication" and "Users" sections of
 * contracts/openapi.yaml exactly (paths, schemas, status codes).
 *
 * Session model: server-side session backed by an HttpOnly `ah_session`
 * cookie (see http.ts — every request is sent with `credentials: "include"`).
 * There is no JWT / bearer token flow for the browser client.
 */
import { http } from "./http";

export type OtpPurpose = "REGISTRATION" | "LOGIN" | "RECOVERY";

/** ADR-0007. The role chosen in the sign-up wizard's first step. */
export type AccountKind = "INDIVIDUAL" | "LEGAL_ENTITY" | "INVESTOR";

/** ADR-0007. Gates the role-specific workspace; login itself is unaffected. */
export type RegistrationReviewStatus = "PENDING" | "APPROVED" | "REJECTED";

/** ADR-0007. Freeform, shape depends on accountKind -- see sign-up.tsx's per-role forms. */
export type Anketa = Record<string, unknown>;

export interface PrivacySettings {
  phoneRevealMode?: "ALWAYS" | "ON_REQUEST" | "NEVER";
}

export interface NotificationPreferences {
  email?: boolean;
  webPush?: boolean;
  sms?: boolean;
}

/** `#/components/schemas/Account` */
export interface Account {
  id: string;
  phoneNumber: string | null;
  email: string | null;
  displayName: string | null;
  status: "ACTIVE" | "SUSPENDED" | "CLOSED";
  privacySettings?: PrivacySettings;
  notificationPreferences?: NotificationPreferences;
  ownedProfileIds: string[];
  roles: string[];
  createdAt: string;
  /** ADR-0007. */
  accountKind?: AccountKind | null;
  reviewStatus?: RegistrationReviewStatus | null;
  reviewReason?: string | null;
}

/** `#/components/schemas/Session` */
export interface AuthSession {
  id: string;
  actingProfileId: string | null;
  ipAddress: string | null;
  userAgent: string | null;
  current: boolean;
  createdAt: string;
  expiresAt: string;
}

/** `#/components/schemas/SessionEstablished` */
export interface SessionEstablished {
  account: Account;
  session: AuthSession;
  sessionToken?: string | null;
}

export const authApi = {
  /** POST /auth/otp — dispatches an SMS OTP. Always 202, never reveals whether the phone is registered. */
  requestOtp(phoneNumber: string, purpose: OtpPurpose): Promise<void> {
    return http.post<void>("/auth/otp", { phoneNumber, purpose });
  },

  /** POST /auth/otp/verify — verifies the OTP and establishes a session (cookie). ADR-0007:
   * accountKind/anketa only matter the first time (REGISTRATION, no existing account yet). */
  verifyOtp(
    phoneNumber: string,
    code: string,
    purpose: OtpPurpose,
    accountKind?: AccountKind,
    anketa?: Anketa,
  ): Promise<SessionEstablished> {
    return http.post<SessionEstablished>(
      "/auth/otp/verify",
      { phoneNumber, code, purpose, ...(accountKind ? { accountKind, anketa } : {}) },
      { idempotent: true },
    );
  },

  /** POST /auth/register/email — creates an account pending email confirmation. No session yet (202). */
  registerEmail(
    email: string,
    password: string,
    displayName?: string,
    accountKind?: AccountKind,
    anketa?: Anketa,
  ): Promise<void> {
    return http.post<void>(
      "/auth/register/email",
      {
        email,
        password,
        ...(displayName ? { displayName } : {}),
        ...(accountKind ? { accountKind, anketa } : {}),
      },
      { idempotent: true },
    );
  },

  /** POST /auth/login/email — authenticates an email/password account and establishes a session. */
  loginEmail(email: string, password: string): Promise<SessionEstablished> {
    return http.post<SessionEstablished>("/auth/login/email", { email, password });
  },

  /** POST /auth/login/google — exchanges a Google authorization code for a first-party session. */
  loginGoogle(authorizationCode: string, redirectUri: string): Promise<SessionEstablished> {
    return http.post<SessionEstablished>("/auth/login/google", { authorizationCode, redirectUri });
  },

  /** POST /auth/logout — revokes the current session; clears the cookie. */
  logout(): Promise<void> {
    return http.post<void>("/auth/logout");
  },

  /** POST /auth/recovery — starts phone or email based account recovery. */
  startRecovery(identifier: { phoneNumber?: string; email?: string }): Promise<void> {
    return http.post<void>("/auth/recovery", identifier);
  },

  /** GET /me — the authenticated account. Throws ApiError(401) when there is no session. */
  me(): Promise<Account> {
    return http.get<Account>("/me");
  },

  /** POST /me/sessions/switch-profile — sets the session's `actingProfileId`. A LEGAL_ENTITY
   * account must switch into a business profile before creating a listing on its behalf,
   * otherwise `POST /listings` creates the listing in personal context (`ownerProfileId=null`). */
  switchActingProfile(actingProfileId: string | null): Promise<AuthSession> {
    return http.post<AuthSession>("/me/sessions/switch-profile", { actingProfileId });
  },

  /** PATCH /me — display name / email. */
  updateMe(input: { displayName?: string; email?: string }): Promise<Account> {
    return http.patch<Account>("/me", input);
  },

  /** PUT /me/password — changes the password for an email-credential account. */
  changePassword(currentPassword: string, newPassword: string): Promise<void> {
    return http.put<void>("/me/password", { currentPassword, newPassword });
  },

  /** PUT /me/preferences — notification channel opt-ins and phone-reveal privacy. */
  updatePreferences(input: {
    privacySettings?: PrivacySettings;
    notificationPreferences?: NotificationPreferences;
  }): Promise<Account> {
    return http.put<Account>("/me/preferences", input);
  },

  /** DELETE /me/account — closes (anonymises) the account; does not delete the row. */
  closeAccount(): Promise<void> {
    return http.delete<void>("/me/account");
  },

  /** GET /me/sessions — active sessions (login history / device list). */
  listSessions(): Promise<AuthSession[]> {
    return http.get<AuthSession[]>("/me/sessions");
  },

  /** DELETE /me/sessions/{id} — revokes a specific session (remote logout). */
  revokeSession(sessionId: string): Promise<void> {
    return http.delete<void>(`/me/sessions/${sessionId}`);
  },
};

/** ADR-0007. `#/components/schemas/RegistrationQueueItem`. */
export interface RegistrationQueueItem {
  id: string;
  phoneNumber: string | null;
  email: string | null;
  displayName: string | null;
  accountKind: AccountKind;
  anketa: Anketa;
  createdAt: string;
}

export interface RegistrationQueuePage {
  items: RegistrationQueueItem[];
  page: { limit: number; nextCursor: string | null; total: number | null };
}

/** ADR-0007. Reviewer-only (`identity:registration:review`) -- `/admin/registration-queue*`. */
export const registrationReviewApi = {
  listQueue(cursor?: string, limit = 20): Promise<RegistrationQueuePage> {
    return http.get<RegistrationQueuePage>("/admin/registration-queue", {
      params: { cursor, limit },
    });
  },
  decide(
    accountId: string,
    outcome: "APPROVED" | "REJECTED",
    reason?: string,
  ): Promise<{ id: string; status: string }> {
    return http.post(
      `/admin/registration-queue/${accountId}/decision`,
      { outcome, ...(reason ? { reason } : {}) },
      { idempotent: true },
    );
  },
};
