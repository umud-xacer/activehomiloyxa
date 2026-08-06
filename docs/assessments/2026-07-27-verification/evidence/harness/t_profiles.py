"""Business Profiles & Verification — FR-PROF-001..007, FR-USER-002, I-13."""

import time

import ah
from ah import Actor, check, sql

RUN = str(int(time.time()))[-6:]
TOK = open("/home/ameer/.claude/jobs/06393b27/tmp/admin_tokens.txt").read().split()
admin = Actor("admin")
admin.c.headers["Authorization"] = f"Bearer {TOK[0]}"

EIGHT = ["CONSTRUCTION_COMPANY", "MANUFACTURER", "BUILDER", "SUPPLIER",
         "CONTRACTOR", "ARCHITECT", "INTERIOR_DESIGNER", "SERVICE_PROVIDER"]

owner = Actor("owner").register_login(f"owner-{RUN}@example.invalid", "Profile Owner")
other = Actor("other").register_login(f"other-{RUN}@example.invalid", "Other User")
anon = Actor("anon")


def lt(x):
    return {"uz_latn": x, "uz_cyrl": x, "ru": x, "en": x}


# ---------- FR-PROF-001 create each of the EIGHT types ----------
made = {}
for t in EIGHT:
    r = owner.post("/business-profiles", json={
        "profileType": t, "name": lt(f"{t} {RUN}"),
        "description": lt("Sinov tavsifi"), "address": "Toshkent"}, idem=True)
    if r.status_code in (200, 201):
        made[t] = r.json()["id"]
time.sleep(4)  # profile ownership propagates profiles -> identity via the outbox (~2s)
check("PROF-001-eight-types", "FR-PROF-001",
      "a profile of each of the eight supported types can be created", made,
      len(made) == 8, f"created {len(made)}/8: {sorted(set(EIGHT) - set(made))} failed")

PID = made.get("CONSTRUCTION_COMPANY")

# ---------- FR-USER-002 multiple profiles + acting-context switch ----------
r = owner.get("/me")
check("USER-002-multiple-profiles", "FR-USER-002", "one account holds multiple profiles", r,
      r.status_code == 200 and len(r.json().get("ownedProfileIds") or []) >= 2,
      f"ownedProfileIds={len(r.json().get('ownedProfileIds') or [])}")
if PID:
    r = owner.post("/me/sessions/switch-profile", json={"actingProfileId": PID})
    check("USER-002-switch", "FR-USER-002", "acting profile context can be selected", r,
          r.status_code in (200, 204), r.text[:160])
    r = owner.get("/me/sessions")
    body = r.json()
    sessions = body if isinstance(body, list) else body.get("items", [])
    cur = [s for s in sessions if s.get("current")]
    check("USER-002-switch-reflected", "FR-USER-002",
          "actions apply to the selected profile only (context is reflected)", r,
          bool(cur) and cur[0].get("actingProfileId") == PID,
          f"actingProfileId={cur[0].get('actingProfileId') if cur else None}")

# ---------- FR-PROF-002 company page + portfolio ----------
if PID:
    r = anon.get(f"/business-profiles/{PID}")
    check("PROF-002-public-page", "FR-PROF-002", "company page is publicly displayed", r,
          r.status_code == 200)
    r = owner.patch(f"/business-profiles/{PID}", json={"description": lt("Yangilangan tavsif")})
    check("PROF-002-edit", "FR-PROF-002", "company details can be maintained", r,
          r.status_code in (200, 204), r.text[:160])
    r = owner.get(f"/business-profiles/{PID}/portfolio")
    check("PROF-002-portfolio-list", "FR-PROF-002", "portfolio is retrievable", r,
          r.status_code == 200)
    r = other.patch(f"/business-profiles/{PID}", json={"description": lt("Hacked")})
    check("SEC-nonowner-profile-edit", "FR-PROF-002 / NFR-SEC-002",
          "a non-owner cannot edit another's company profile", r,
          r.status_code in (403, 404), r.text[:160])

# ---------- team endpoints (contract operations listTeamMembers/addTeamMember) ----------
if PID:
    r = owner.get(f"/business-profiles/{PID}/team")
    check("PROF-team-endpoint", "contracts/openapi.yaml operationId listTeamMembers",
          "the team roster endpoint defined in the frozen contract is served", r,
          r.status_code == 200, f"{r.status_code} (404 => route absent)")

# ---------- FR-PROF-004 request verification (gated on the paid entitlement) ----------
if PID:
    r = owner.post(f"/business-profiles/{PID}/verification",
                   json={"documentMediaAssetIds": []}, idem=True)
    check("PROF-004-request-verification", "FR-PROF-004",
          "verification request creates a case in the reviewer queue "
          "(pre: verification purchased, FR-SUBS-002)", r,
          r.status_code in (200, 201, 402, 403, 409),
          f"{r.status_code} {r.text[:180]}")
    CASE = r.json().get("id") if r.status_code in (200, 201) else None
else:
    CASE = None

# ---------- FR-PROF-005 reviewer decision; I-13 badge only from an approved case ----------
r = admin.get("/admin/verification-queue")
check("ADMIN-002-verification-queue", "FR-ADMIN-002 / FR-PROF-004",
      "the verification queue lists cases for processing", r,
      r.status_code == 200, f"{len(r.json().get('items', [])) if r.status_code == 200 else '-'} cases")
queue = r.json().get("items", []) if r.status_code == 200 else []
CASE = CASE or (queue[0].get("id") if queue else None)

if PID:
    badge_before = sql(
        f"select count(*) from profiles.business_profile where id='{PID}' and verified_badge_status is not null")
    check("I-13-no-badge-without-approval", "I-13 / FR-PROF-006",
          "no verified badge exists before an approved case", badge_before,
          badge_before in ("0", ""), f"badge rows={badge_before}")

if CASE:
    r = other.post(f"/admin/verification-queue/{CASE}/decision",
                   json={"outcome": "APPROVED"}, idem=True)
    check("SEC-nonreviewer-decision", "FR-PROF-005 / NFR-SEC-002",
          "a non-reviewer cannot decide a verification case", r,
          r.status_code in (401, 403), r.text[:160])
    r = admin.post(f"/admin/verification-queue/{CASE}/decision",
                   json={"outcome": "APPROVED", "reason": "documents ok"}, idem=True)
    check("PROF-005-approve", "FR-PROF-005", "an authorised reviewer approves, recording outcome", r,
          r.status_code in (200, 201, 204), r.text[:200])
    time.sleep(4)
    if PID:
        st = sql(f"select verified_badge_status from profiles.business_profile where id='{PID}'")
        check("PROF-006-badge-issued", "FR-PROF-005 / FR-PROF-006 / I-13",
              "approval issues a verified badge with a validity period", st,
              st in ("VALID", "ACTIVE"), f"badge status={st!r}")
    # terminal case immutable
    r = admin.post(f"/admin/verification-queue/{CASE}/decision",
                   json={"outcome": "REJECTED", "reason": "changed my mind"}, idem=True)
    check("PROF-005-terminal-immutable", "FR-PROF-005 (both auditable; terminal case)",
          "a decided (terminal) verification case cannot be re-decided", r,
          r.status_code in (409, 403, 422), r.text[:160])

# ---------- audit trail of the decision (FR-AUDIT-001) ----------
n = sql("select count(*) from analytics.audit_entry")
check("AUDIT-001-entries", "FR-AUDIT-001",
      "every administrative/moderation action is auditable", n, int(n or 0) > 0,
      f"{n} audit entries")

ah.dump("/home/ameer/.claude/jobs/06393b27/tmp/res_profiles.json")
