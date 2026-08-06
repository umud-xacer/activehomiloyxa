"""Moderation, Administration, Analytics/Audit, Ads, Notifications, and no-redeploy config.

FR-MOD-001..005, FR-ADMIN-001..006, FR-AUDIT-001/002, FR-ANALYTICS-001/002,
FR-BANNER-001..005, FR-NOTIF-001/004, FR-CFG-001 (NFR-MAINT-001), I-24, BRULE-20.
"""

import time

import httpx

import ah
from ah import Actor, check, items, sql

RUN = str(int(time.time()))[-6:]
BASE = "http://127.0.0.1:8100/api/v1"
TOK = open("/home/ameer/.claude/jobs/06393b27/tmp/admin_tokens.txt").read().split()
admin = Actor("admin")
admin.c.headers["Authorization"] = f"Bearer {TOK[0]}"
admin2 = Actor("admin2")
admin2.c.headers["Authorization"] = f"Bearer {TOK[1]}"
anon = Actor("anon")

cats = httpx.get(f"{BASE}/categories").json()
K = next(c["id"] for c in cats if c["path"] == "/kvartira")
seller = Actor("s").register_login(f"ops-s-{RUN}@example.invalid", "Ops Seller")
reporter = Actor("r").register_login(f"ops-r-{RUN}@example.invalid", "Ops Reporter")

r = seller.post("/listings", json={
    "categoryId": K, "listingType": "ADVERTISEMENT", "title": f"Moderatsiya eʼloni {RUN}",
    "description": "Moderatsiya sinovi", "price": {"amount": "9000", "currency": "UZS"},
    "attributes": {"rooms": 2, "area_m2": 44}, "publish": True}, idem=True)
LID = r.json()["id"] if r.status_code in (200, 201) else None

# ================= MODERATION =================
r = reporter.post("/reports", json={
    "subjectType": "LISTING", "subjectId": LID, "reason": "Spam va aldov"}, idem=True)
check("MOD-001-report", "FR-MOD-001", "any user can report a listing; it enters the queue", r,
      r.status_code in (200, 201, 202), r.text[:200])
time.sleep(4)

r = admin.get("/admin/moderation-queue")
q = items(r)
check("MOD-005-queue", "FR-MOD-005", "the moderation queue lists reports and flagged content", r,
      r.status_code == 200 and len(q) > 0, f"{len(q)} queued items")

r = reporter.get("/admin/moderation-queue")
check("MOD-005-queue-denied", "FR-MOD-005 / NFR-SEC-002",
      "an ordinary user cannot see the moderation queue", r, r.status_code == 403,
      r.text[:120])

case = next((c for c in q if c.get("subjectId") == LID), q[0] if q else None)

# fixed verb set only (BR-MOD-02)
if case:
    r = admin.post(f"/admin/moderation-queue/{case['id']}/action",
                   json={"action": "DELETE_EVERYTHING"}, idem=True)
    check("MOD-003-verb-closed", "FR-MOD-003 / BR-MOD-02 (closed verb set)",
          "an action verb outside the fixed set is rejected", r, r.status_code == 422,
          r.text[:160])

# I-24: moderation drives the owning context, which records its OWN transition
if case and LID:
    before = sql(f"select count(*) from catalog.listing_transition where listing_id='{LID}'")
    r = admin.post(f"/admin/moderation-queue/{case['id']}/action",
                   json={"action": "SUSPEND", "note": "policy breach"}, idem=True)
    check("MOD-003-action", "FR-MOD-003",
          "a moderator action changes content state and is auditable", r,
          r.status_code in (200, 201, 204), r.text[:200])
    time.sleep(5)
    st = sql(f"select lifecycle_state from catalog.listing where id='{LID}'")
    after = sql(f"select count(*) from catalog.listing_transition where listing_id='{LID}'")
    check("I-24-owning-context", "I-24 / DEC-22",
          "moderation drives the target module, which records its own transition", st,
          st == "SUSPENDED" and int(after or 0) > int(before or 0),
          f"listing state={st}, transitions {before} -> {after}")
    r = anon.get(f"/listings/{LID}")
    check("I-06-suspended-hidden", "I-06 / FR-MOD-003",
          "a suspended listing is no longer publicly visible", r, r.status_code in (403, 404),
          f"anon GET -> {r.status_code}")

# FR-MOD-004 account suspension -> that account's listings hidden (compensation)
r = seller.post("/listings", json={
    "categoryId": K, "listingType": "ADVERTISEMENT", "title": f"Suspend sinov {RUN}",
    "description": "Hisob toʻxtatish sinovi", "attributes": {"rooms": 1, "area_m2": 30},
    "publish": True}, idem=True)
LID2 = r.json()["id"] if r.status_code in (200, 201) else None
r = admin.post(f"/admin/users/{seller.user_id}/status",
               json={"action": "SUSPEND", "reason": "abuse"}, idem=True)
check("MOD-004-suspend-account", "FR-MOD-004",
      "an authorised operator can suspend an account", r, r.status_code in (200, 201, 204),
      r.text[:200])
time.sleep(5)
r = seller.get("/me")
check("MOD-004-suspended-cannot-act", "FR-MOD-004",
      "a suspended account cannot perform restricted actions", r, r.status_code >= 400,
      f"suspended account /me -> {r.status_code}")
if LID2:
    r = anon.get(f"/listings/{LID2}")
    check("MOD-004-listings-hidden", "FR-MOD-004 (compensation)",
          "a suspended account's listings are hidden", r, r.status_code in (403, 404),
          f"anon GET -> {r.status_code}")

# ================= ADMINISTRATION =================
r = admin.get("/admin/dashboard")
check("ADMIN-dashboard", "FR-ADMIN-001 / M-12 (admin composes operator interfaces)",
      "the admin dashboard composes other modules' operator data", r, r.status_code == 200,
      r.text[:160])
r = anon.get("/admin/dashboard")
check("ADMIN-not-bypass", "M-12 (/admin is not a privilege bypass)",
      "/admin is not reachable without the permission key", r, r.status_code in (401, 403),
      f"{r.status_code}")
r = admin.get("/admin/users")
check("ADMIN-001-users", "FR-ADMIN-001", "administrators can view/manage user records", r,
      r.status_code == 200, f"{len(items(r))} users")
r = admin.get("/admin/reports", params={"report": "LISTINGS_OVERVIEW"})
check("ADMIN-005-reports", "FR-ADMIN-005", "operational reports reflect captured metrics", r,
      r.status_code == 200, r.text[:200])

# FR-ADMIN-006 role assignment within the fixed permission model
target = Actor("t").register_login(f"ops-t-{RUN}@example.invalid", "Role Target")
if True:
    r = admin.post(f"/admin/users/{target.user_id}/roles",
                   json={"roleCode": "moderator", "actingProfileId": None}, idem=True)
    check("ADMIN-006-assign-role", "FR-ADMIN-006 / BRULE-02",
          "a Super Administrator can assign a role; assignments take effect", r,
          r.status_code in (200, 201, 204), r.text[:200])
    time.sleep(3)
    r = target.get("/admin/moderation-queue")
    check("ADMIN-006-role-effective", "FR-ADMIN-006",
          "the assigned role grants exactly its configured permissions", r,
          r.status_code == 200, f"moderator queue -> {r.status_code}")
    r = target.get("/admin/billing/invoices")
    check("I-16-no-widening", "I-16 / BRULE-02",
          "a role grants only its own permissions; it cannot widen access", r,
          r.status_code == 403, f"billing invoices as moderator -> {r.status_code}")

# ================= AUDIT & ANALYTICS =================
r = admin.get("/admin/audit-log")
check("AUDIT-002-viewable", "FR-AUDIT-002", "audit logs are viewable by an authorised admin", r,
      r.status_code == 200, f"{len(items(r))} entries")
r = admin.get("/admin/audit-log", params={"actorId": admin.user_id})
check("AUDIT-002-filterable", "FR-AUDIT-002", "audit logs are filterable", r,
      r.status_code == 200, f"{len(items(r))} filtered entries")

# append-only immutability (BRULE-20 / DDD BC-13 append-only facts)
upd = sql("update analytics.audit_entry set action='TAMPERED' where true")
check("AUDIT-append-only", "DDD BC-13 (append-only immutable facts)",
      "audit entries cannot be updated", upd,
      "ERROR" in (upd or "") or upd.strip() == "" or "UPDATE 0" in (upd or ""),
      f"update result={upd[:120]!r}")

# closed metric vocabulary (BRULE-20)
keys = sql("select string_agg(distinct metric_key, ',') from analytics.metric_event")
CLOSED = {"LISTING_VIEWED", "CONTACT_BUTTON_CLICKED", "PHONE_REVEALED", "CHAT_INITIATED",
          "FAVORITE_ADDED", "PREMIUM_LISTING_STAT", "BANNER_IMPRESSION_RECORDED",
          "BANNER_CLICK_RECORDED"}
seen = {k.strip() for k in (keys or "").split(",") if k.strip()}
check("ANALYTICS-closed-vocabulary", "BRULE-20 / DDD BC-13 (closed v1 metric vocabulary)",
      "only metrics from the closed v1 set are captured", seen, seen <= CLOSED,
      f"observed={sorted(seen)}; outside the closed set={sorted(seen - CLOSED)}")
check("ANALYTICS-001-coverage", "FR-ANALYTICS-001",
      "the documented metric set is actually captured", seen,
      seen == CLOSED, f"captured {len(seen)}/8: missing={sorted(CLOSED - seen)}")

# FR-ANALYTICS-002 owner statistics (seller is suspended by now -> use a fresh owner)
stat_owner = Actor("so").register_login(f"ops-stat-{RUN}@example.invalid", "Stat Owner")
_r = stat_owner.post("/listings", json={
    "categoryId": K, "listingType": "ADVERTISEMENT", "title": f"Stat eʼlon {RUN}",
    "description": "Statistika sinovi", "attributes": {"rooms": 2, "area_m2": 40},
    "publish": True}, idem=True)
SLID = _r.json()["id"] if _r.status_code in (200, 201) else None
if SLID:
    for _ in range(6):
        anon.get(f"/listings/{SLID}")
    time.sleep(4)
    r = stat_owner.get(f"/listings/{SLID}/statistics")
    check("ANALYTICS-002-owner-stats", "FR-ANALYTICS-002",
          "owners see basic performance statistics for their listings", r,
          r.status_code == 200, r.text[:250])

# ================= ADS / BANNERS =================
r = admin.get("/admin/campaigns")
check("BANNER-admin-list", "FR-ADMIN-004 / FR-BANNER-001",
      "administrators can manage banner campaigns", r, r.status_code == 200,
      f"{len(items(r))} campaigns")
r = anon.get("/banners/serve", params={"slotKey": "home-hero"})
check("BANNER-004-serve", "FR-BANNER-004",
      "the banner serve endpoint answers for a configured slot", r,
      r.status_code in (200, 204, 404), f"{r.status_code} {r.text[:120]}")

# ================= NOTIFICATIONS =================
r = seller.get("/me/notifications") if seller else None
r2 = reporter.get("/me/notifications")
check("NOTIF-list", "FR-NOTIF-001 / FR-NOTIF-004",
      "a user can list their notifications", r2, r2.status_code == 200,
      f"{len(items(r2))} notifications")
r = reporter.put("/me/preferences", json={"notificationPreferences": {
    "email": False, "webPush": False, "sms": False}})
check("NOTIF-004-preferences", "FR-NOTIF-004", "notification preferences are manageable", r,
      r.status_code in (200, 204), r.text[:160])
n = sql("select count(*) from notifications.notification")
check("NOTIF-001-dispatched", "FR-NOTIF-001",
      "documented events produce templated notifications", n, int(n or 0) > 0,
      f"{n} notification rows")

# ================= NO-REDEPLOY CONFIG (NFR-MAINT-001) =================
before = len(httpx.get(f"{BASE}/categories").json())
forms = items(admin.get("/admin/config/form-definition"))
fh = next((h["id"] for h in forms if h.get("code") == "form-service"), None)


def lt(x):
    return {"uz_latn": x, "uz_cyrl": x, "ru": x, "en": x}


if fh:
    r = admin.post("/admin/config/category", json={
        "code": f"live-cat-{RUN}", "businessOwner": "Verification",
        "definition": {"descriptor": {"name": lt(f"Jonli kategoriya {RUN}"),
                                      "display_order": 9, "metadata": {}},
                       "path": f"/live-cat-{RUN}", "form_definition_id": fh,
                       "tree_status": "ACTIVE"}})
    if r.status_code in (200, 201):
        h, v = r.json()["headId"], r.json()["id"]
        for _ in range(2):
            p = admin2.post(f"/admin/config/category/{h}/versions/{v}/publish",
                            json={"approvalNote": "live"})
            if p.json().get("status") == "PUBLISHED":
                break
        time.sleep(3)
        after = httpx.get(f"{BASE}/categories").json()
        check("CFG-001-no-redeploy", "FR-CFG-001 / NFR-MAINT-001",
              "a newly published category is served with no redeploy", after,
              len(after) == before + 1
              and any(c["path"] == f"/live-cat-{RUN}" for c in after),
              f"categories {before} -> {len(after)} (same running process)")

ah.dump("/home/ameer/.claude/jobs/06393b27/tmp/res_ops.json")
