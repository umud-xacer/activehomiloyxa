"""End-to-end money path + media: FR-SUBS-002/003, FR-BILL-001/002/003, I-14, I-08,
FR-MEDIA-001..005, FR-ADV-002 (image limits), FR-PROF-003/004/005/006, I-04, I-13."""

import json
import time

import httpx

import ah
from ah import Actor, check, items, sql

RUN = str(int(time.time()))[-6:]
BASE = "http://127.0.0.1:8100/api/v1"
TOK = open("/home/ameer/.claude/jobs/06393b27/tmp/admin_tokens.txt").read().split()
admin = Actor("admin")
admin.c.headers["Authorization"] = f"Bearer {TOK[0]}"

biz = Actor("biz").register_login(f"e2e-{RUN}@example.invalid", "E2E Biz")
prods = httpx.get(f"{BASE}/products").json()
PLAN = next(p["id"] for p in prods if p["productType"] == "SUBSCRIPTION")
VERIF = next(p["id"] for p in prods if p["productType"] == "VERIFICATION")

PID = biz.post("/business-profiles", json={
    "profileType": "CONSTRUCTION_COMPANY",
    "name": {"uz_latn": "Qurilish MChJ", "uz_cyrl": "Қурилиш МЧЖ", "ru": "Строй ООО", "en": "Build LLC"},
    "address": "Toshkent"}, idem=True).json()["id"]
time.sleep(4)
biz.post("/me/sessions/switch-profile", json={"actingProfileId": PID})


def buy(product_id, label, target_type="PROFILE", target_id=None):
    """order -> invoice -> operator confirms offline payment -> entitlement."""
    body = {"productId": product_id, "targetType": target_type}
    if target_id:
        body["targetId"] = target_id
    r = biz.post("/orders", json=body, idem=True)
    check(f"SUBS-002-order-{label}", "FR-SUBS-002", "a pending order is created", r,
          r.status_code in (200, 201), r.text[:200])
    if r.status_code not in (200, 201):
        return None
    order = r.json()
    oid = order["id"]
    check(f"SUBS-002-pending-{label}", "FR-SUBS-002", "order starts unpaid/pending",
          order.get("status"), order.get("status") in ("PENDING", "PENDING_PAYMENT", "UNPAID",
                                                       "AWAITING_PAYMENT", "CREATED", "INVOICED"),
          f"status={order.get('status')}")
    snap = sql(f"select product_snapshot is not null from billing.purchase_order where id='{oid}'")
    check(f"SUBS-002-snapshot-{label}", "DDD BC-08 ProductSnapshot",
          "the order freezes a ProductSnapshot", snap, snap == "t", f"snapshot={snap}")
    r = biz.get(f"/orders/{oid}/invoice")
    check(f"BILL-001-invoice-{label}", "FR-BILL-001", "an invoice is produced", r,
          r.status_code == 200, r.text[:200])
    if r.status_code != 200:
        return None
    inv = r.json()["id"]
    # I-14: buyer cannot self-confirm
    r = biz.post(f"/admin/billing/invoices/{inv}/confirm-payment",
                 json={"confirmed": True, "note": "self"}, idem=True)
    check(f"I-14-self-confirm-denied-{label}", "I-14 / NFR-SEC-002",
          "the buyer cannot confirm their own offline payment", r,
          r.status_code in (401, 403), r.text[:150])
    r = admin.post(f"/admin/billing/invoices/{inv}/confirm-payment",
                   json={"confirmed": True, "note": f"OFFLINE-{label}"}, idem=True)
    check(f"BILL-002-confirm-{label}", "FR-BILL-002",
          "operator records the offline payment confirmation", r,
          r.status_code in (200, 201, 204), r.text[:250])
    time.sleep(5)
    return oid


# ---------- I-14: no entitlement before payment ----------
ent0 = biz.get("/me/entitlements")
n0 = len(items(ent0))
check("I-14-none-before-payment", "I-14 / FR-SUBS-003",
      "no entitlement is active before confirmed payment", ent0, n0 == 0, f"{n0} entitlements")

buy(PLAN, "plan")
ent1 = biz.get("/me/entitlements")
items1 = items(ent1)
check("SUBS-003-activated", "FR-SUBS-003 / I-14",
      "the entitlement activates on administrator payment confirmation", ent1,
      len(items1) > n0, f"{len(items1)} entitlements after confirmation")

r = admin.get("/admin/billing/invoices")
invs = items(r)
check("BILL-003-reconcile", "FR-BILL-003",
      "invoice/payment status is visible and reconcilable in the back office", r,
      r.status_code == 200 and len(invs) > 0, f"{len(invs)} invoices")

# ---------- I-08 quota with an active 2-listing plan ----------
cats = httpx.get(f"{BASE}/categories").json()
K = next(c["id"] for c in cats if c["path"] == "/kvartira")
made, last = 0, None
for i in range(6):
    last = biz.post("/listings", json={
        "categoryId": K, "listingType": "ADVERTISEMENT", "title": f"Kvota {i}",
        "description": "Kvota tekshiruvi", "attributes": {"rooms": 3, "area_m2": 50},
        "publish": True}, idem=True)
    if last.status_code in (200, 201):
        made += 1
    else:
        break
check("I-08-quota", "I-08 / FR-ADV-008 / BRULE-07",
      "creation beyond the plan quota (max_active_listings=2) is refused", last,
      made <= 2 and last.status_code in (403, 409),
      f"created {made} under a 2-listing plan; stopped at {last.status_code}")

# ---------- FR-MEDIA-001/002: presigned upload, images only ----------
LID = None
r = biz.post("/listings", json={
    "categoryId": K, "listingType": "ADVERTISEMENT", "title": "Media sinov",
    "description": "Rasm sinovi", "attributes": {"rooms": 2, "area_m2": 40}}, idem=True)
if r.status_code in (200, 201):
    LID = r.json()["id"]

for ct, ok_expected, label in [("image/jpeg", True, "jpeg"), ("image/png", True, "png"),
                               ("video/mp4", False, "video"), ("application/pdf", False, "pdf")]:
    r = biz.post("/media/uploads", json={
        "contentType": ct, "sizeBytes": 2048, "ownerContextType": "LISTING"}, idem=True)
    if ok_expected:
        check(f"MEDIA-001-{label}", "FR-MEDIA-001", "valid image upload target is issued", r,
              r.status_code in (200, 201), r.text[:160])
    else:
        check(f"MEDIA-002-{label}", "FR-MEDIA-002 / DEC-10 / BRULE-11",
              "video/PDF upload is refused with a clear message", r,
              r.status_code >= 400, r.text[:160])

r = biz.post("/media/uploads", json={
    "contentType": "image/jpeg", "sizeBytes": 20 * 1024 * 1024, "ownerContextType": "LISTING"},
    idem=True)
check("MEDIA-001-oversize", "FR-MEDIA-001", "oversized image (>10MB) is rejected", r,
      r.status_code >= 400, r.text[:160])


def upload_image(context="LISTING"):
    """Full presigned round trip: init -> PUT bytes to MinIO."""
    r = biz.post("/media/uploads", json={
        "contentType": "image/png", "sizeBytes": 70, "ownerContextType": context}, idem=True)
    if r.status_code not in (200, 201):
        return None, r
    d = r.json()
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d494844520000000100000001080600000"
        "01f15c4890000000a49444154789c6360000002000100" "05fe02fea7"
        "35817d0000000049454e44ae426082")
    put = httpx.put(d["uploadUrl"], content=png,
                    headers={**(d.get("headers") or {}), "Content-Type": "image/png"},
                    timeout=30)
    return d["mediaAssetId"], put


mid, put = upload_image()
check("MEDIA-001-presigned-put", "FR-MEDIA-001 / Security Arch (presigned direct upload)",
      "the client can PUT bytes directly to the presigned MinIO URL", put,
      put is not None and put.status_code in (200, 201, 204),
      f"PUT {put.status_code if put is not None else 'n/a'}")

# ---------- FR-ADV-002 / I-04: at most 10 images ----------
if mid:
    if not LID:
        LID = items(biz.get("/me/listings"))[0]["id"]
    attached, lastr = 0, None
    for i in range(11):
        m, p = upload_image()
        if not m:
            break
        time.sleep(0.3)
        lastr = biz.post(f"/listings/{LID}/images",
                         json={"mediaAssetId": m, "position": i + 1}, idem=True)
        if lastr.status_code in (200, 201, 204):
            attached += 1
        else:
            break
    check("ADV-002-image-limit", "FR-ADV-002 / I-04 / BRULE-06",
          "up to 10 images accepted; the 11th refused", lastr,
          attached == 10 and lastr is not None and lastr.status_code >= 400,
          f"attached {attached}; 11th -> {lastr.status_code if lastr is not None else 'n/a'}")

# ---------- FR-PROF-003/004: verification gated on the paid entitlement ----------
buy(VERIF, "verification")
ents = items(biz.get("/me/entitlements"))
vent = next((e for e in ents if e.get("entitlementType") == "VERIFICATION_ELIGIBILITY"), None)
check("PROF-004-verification-entitlement", "FR-PROF-004 (pre: verification purchased)",
      "a VERIFICATION entitlement is active after payment confirmation", vent,
      vent is not None, f"entitlements={json.dumps(ents)[:300]}")

doc_id, _ = upload_image("VERIFICATION_DOCUMENT")
if vent and doc_id:
    r = biz.post(f"/business-profiles/{PID}/verification", json={
        "entitlementId": vent.get("id"),
        "documents": [{"mediaAssetId": doc_id, "documentKind": "REGISTRATION_CERTIFICATE", "position": 1}]},
        idem=True)
    check("PROF-004-request", "FR-PROF-004",
          "verification request creates a case in the reviewer queue", r,
          r.status_code in (200, 201), r.text[:250])
    time.sleep(3)
    q = items(admin.get("/admin/verification-queue"))
    case = next((c for c in q if c.get("businessProfileId") == PID), None)
    check("ADMIN-002-case-queued", "FR-ADMIN-002 / FR-PROF-004",
          "the request appears in the verification queue", case, case is not None,
          f"{len(q)} cases in queue")
    if case:
        badge0 = sql(f"select badge_status from profiles.business_profile where id='{PID}'")
        check("I-13-no-badge-yet", "I-13", "no badge before the case is approved", badge0,
              badge0 in ("", "NONE", "null"), f"badge={badge0!r}")
        r = admin.post(f"/admin/verification-queue/{case['id']}/decision",
                       json={"outcome": "APPROVED", "reason": "documents verified"}, idem=True)
        check("PROF-005-approve", "FR-PROF-005", "reviewer approves, recording the outcome", r,
              r.status_code in (200, 201, 204), r.text[:200])
        time.sleep(5)
        badge = sql(f"select badge_status from profiles.business_profile where id='{PID}'")
        until = sql(f"select badge_valid_until from profiles.business_profile where id='{PID}'")
        check("PROF-006-badge", "FR-PROF-005 / FR-PROF-006 / I-13",
              "approval issues a verified badge with a validity period", badge,
              badge in ("VALID", "ACTIVE") and until not in ("", None),
              f"badge={badge!r} validUntil={until!r}")
        r = admin.post(f"/admin/verification-queue/{case['id']}/decision",
                       json={"outcome": "REJECTED", "reason": "re-decide"}, idem=True)
        check("PROF-005-terminal", "FR-PROF-005 / Config: terminal cases immutable",
              "a terminal verification case cannot be re-decided", r,
              r.status_code in (403, 409, 422), r.text[:160])

ah.dump("/home/ameer/.claude/jobs/06393b27/tmp/res_e2e.json")
