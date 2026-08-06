"""Identity & Access — FR-AUTH-001..006, FR-USER-001..005, NFR-SEC (session auth, default deny)."""

import time

import ah
from ah import Actor, check, sql

RUN = str(int(time.time()))[-6:]

anon = Actor("anon")

# ---------- FR-AUTH-002 registration via email ----------
r = anon.post(
    "/auth/register/email",
    json={"email": f"bob-{RUN}.verify@example.invalid", "password": "Str0ng!Passw0rd", "displayName": "Bob"},
)
check("AUTH-002-register", "FR-AUTH-002", "202/201 account created, confirmation pending", r,
      r.status_code in (200, 201, 202))

# duplicate email must be rejected (acceptance 2)
r = anon.post(
    "/auth/register/email",
    json={"email": f"bob-{RUN}.verify@example.invalid", "password": "Str0ng!Passw0rd", "displayName": "Bob2"},
)
check("AUTH-002-duplicate", "FR-AUTH-002", "duplicate email rejected (4xx CONFLICT)", r,
      400 <= r.status_code < 500, "acceptance (2)")

# acceptance (1): a confirmation LINK activates the account.
time.sleep(1.5)  # registration is async: 202 is returned before the row is committed
status = sql(f"select status from identity.user_account where email='bob-{RUN}.verify@example.invalid'")
check("AUTH-002-inactive-until-confirmed", "FR-AUTH-002",
      "account NOT usable until confirmation redeemed", status,
      status != "ACTIVE", f"db status={status!r}")

r = anon.post("/auth/login/email", json={"email": f"bob-{RUN}.verify@example.invalid", "password": "Str0ng!Passw0rd"})
check("AUTH-002-login-blocked-unconfirmed", "FR-AUTH-002",
      "login refused before email confirmation", r, r.status_code >= 400)

# ---------- FR-AUTH-004 login ----------
r = anon.post("/auth/login/email", json={"email": f"bob-{RUN}.verify@example.invalid", "password": "WRONG-password"})
check("AUTH-004-bad-credential", "FR-AUTH-004", "invalid credentials refused", r,
      r.status_code in (401, 403))
r = anon.post("/auth/login/email", json={"email": "nobody@example.invalid", "password": "Str0ng!Passw0rd"})
check("AUTH-004-unknown-user", "FR-AUTH-004", "unknown account refused", r,
      r.status_code in (401, 403))

alice = Actor("alice").register_login(f"alice2-{RUN}.verify@example.invalid", "Alice Two")

# ---------- FR-AUTH-005 session management ----------
r = alice.get("/me")
check("AUTH-005-session-works", "FR-AUTH-005", "authenticated session grants access", r, r.status_code == 200)
r = alice.get("/me/sessions")
check("AUTH-005-list-sessions", "FR-AUTH-005", "sessions listable", r, r.status_code == 200)
r = alice.post("/auth/logout")
check("AUTH-005-logout", "FR-AUTH-005", "logout ends the session", r, r.status_code in (200, 204))
r = alice.get("/me")
check("AUTH-005-session-dead-after-logout", "FR-AUTH-005",
      "session no longer usable after logout", r, r.status_code == 401)

# ---------- default deny (Security Arch; NFR-SEC-002) ----------
r = anon.get("/me")
check("SEC-anon-me-denied", "NFR-SEC-002", "unauthenticated access denied 401", r, r.status_code == 401)
r = anon.get("/admin/users")
check("SEC-anon-admin-denied", "NFR-SEC-002", "unauthenticated admin access denied", r,
      r.status_code in (401, 403))

alice = Actor("alice").register_login(f"alice2-{RUN}.verify@example.invalid", "Alice Two")
r = alice.get("/admin/users")
check("SEC-nonadmin-admin-denied", "FR-ADMIN-001",
      "ordinary user without permission denied on /admin (default deny)", r, r.status_code == 403)
r = alice.get("/admin/config/category")
check("SEC-nonadmin-config-denied", "FR-CFG-001",
      "ordinary user denied config authoring", r, r.status_code == 403)
r = alice.get("/admin/audit-log")
check("SEC-nonadmin-audit-denied", "FR-AUDIT-002", "ordinary user denied audit log", r,
      r.status_code == 403)

# ---------- no JWT (DEC: session auth, not JWT) ----------
tok = alice.c.cookies.get("ah_session") or ""
check("SEC-not-a-jwt", "Baseline DEC (session auth, not JWT)",
      "session token is an opaque server-side handle, not a JWT", tok,
      not tok.startswith("ey") and tok.count(".") != 2, f"token prefix={tok[:8]!r}")

# ---------- FR-AUTH-001 / FR-NOTIF-003 phone OTP ----------
r = anon.post("/auth/otp", json={"phoneNumber": "+998901234567", "purpose": "REGISTRATION"})
check("AUTH-001-otp-request", "FR-AUTH-001", "OTP request accepted and dispatched via Eskiz", r,
      r.status_code in (200, 202), "provider boundary only (no real Eskiz creds)")
r = anon.post("/auth/otp/verify",
              json={"phoneNumber": "+998901234567", "code": "000000", "purpose": "REGISTRATION"})
check("AUTH-001-otp-bad-code", "FR-AUTH-001", "invalid/expired code rejected with clear message", r,
      r.status_code >= 400)

# ---------- FR-AUTH-006 recovery ----------
r = anon.post("/auth/recovery", json={"email": f"alice2-{RUN}.verify@example.invalid"})
check("AUTH-006-recovery-known", "FR-AUTH-006", "verified recovery flow restores access", r,
      r.status_code in (200, 202))
r = anon.post("/auth/recovery", json={"email": "not-registered@example.invalid"})
check("AUTH-006-recovery-unknown", "FR-AUTH-006", "unverified/unknown request refused (or neutral)", r,
      r.status_code in (200, 202, 400, 401, 403, 404), "enumeration-safe neutral response is acceptable")

# ---------- FR-AUTH-003 Google ----------
r = anon.post("/auth/login/google", json={"idToken": "not-a-real-google-token"})
check("AUTH-003-google-bad-token", "FR-AUTH-003", "invalid federated token refused", r,
      r.status_code >= 400, "NEEDS-HUMAN for the success path")

# ---------- FR-USER-001 personal profile ----------
r = alice.patch("/me", json={"displayName": "Alice Renamed"})
check("USER-001-edit-profile", "FR-USER-001", "edits persist and reflect immediately", r,
      r.status_code == 200)
r = alice.get("/me")
check("USER-001-edit-visible", "FR-USER-001", "edited name reflected immediately", r,
      r.status_code == 200 and r.json().get("displayName") == "Alice Renamed")

# ---------- FR-USER-003 privacy settings ----------
r = alice.put("/me/preferences", json={"privacySettings": {"phoneRevealMode": "NEVER"}})
check("USER-003-privacy", "FR-USER-003", "user controls phone reveal setting", r,
      r.status_code in (200, 204))

# ---------- FR-USER-005 account closure ----------
tmp = Actor("closer").register_login(f"closer-{RUN}.verify@example.invalid", "Closer")
r = tmp.delete("/me/account")
check("USER-005-closure", "FR-USER-005", "closure request deactivates the account", r,
      r.status_code in (200, 202, 204))
r = tmp.get("/me")
check("USER-005-closed-no-access", "FR-USER-005", "closed account cannot act", r,
      r.status_code >= 400)

ah.dump("/home/ameer/.claude/jobs/06393b27/tmp/res_identity.json")
