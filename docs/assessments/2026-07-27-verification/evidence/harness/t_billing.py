"""Billing & Entitlements — FR-SUBS-001..004, FR-BILL-001..004, I-14, plus I-08 quota."""

import time

import httpx

import ah
from ah import Actor, check, sql

RUN = str(int(time.time()))[-6:]
BASE = "http://127.0.0.1:8100/api/v1"
TOK = open("/home/ameer/.claude/jobs/06393b27/tmp/admin_tokens.txt").read().split()
admin = Actor("admin")
admin.c.headers["Authorization"] = f"Bearer {TOK[0]}"

biz = Actor("biz").register_login(f"biz-{RUN}@example.invalid", "Biz User")
anon = Actor("anon")

# ---------- FR-SUBS-001 all six product types presented ----------
r = anon.get("/products")
prods = r.json() if r.status_code == 200 else []
types = {p["productType"] for p in prods}
check("SUBS-001-six-types", "FR-SUBS-001",
      "all six monetisation product types presented with configured pricing", r,
      types == {"SUBSCRIPTION", "PREMIUM", "FEATURED", "TOP_PLACEMENT", "VERIFICATION",
                "BANNER_PLACEMENT"}, f"types={sorted(types)}")
check("SUBS-001-priced", "FR-SUBS-001", "products carry configured pricing", r,
      all(p.get("price", {}).get("amount") for p in prods), f"{len(prods)} products")

PLAN = next((p["id"] for p in prods if p["productType"] == "SUBSCRIPTION"), None)
VERIF = next((p["id"] for p in prods if p["productType"] == "VERIFICATION"), None)

# ---------- FR-BILL-004 no online payment path exists ----------
paths = set(httpx.get("http://127.0.0.1:8100/openapi.json").json()["paths"])
online = [p for p in paths
          if any(k in p.lower() for k in ("payment-intent", "checkout", "gateway", "stripe",
                                          "/payme", "card-payment", "webhook/pay", "acquir"))]
check("BILL-004-no-online-gateway", "FR-BILL-004 / I-14 / DEC-02",
      "no online payment path exists in v1", online, online == [], f"suspect paths={online}")

# ---------- FR-SUBS-002 purchase request creates a pending order ----------
r = biz.post("/orders", json={"productId": PLAN, "targetType": "PROFILE"}, idem=True)
check("SUBS-002-create-order", "FR-SUBS-002", "a pending order is created", r,
      r.status_code in (200, 201), r.text[:250])
ORDER = r.json().get("id") if r.status_code in (200, 201) else None
if ORDER:
    st = r.json().get("status")
    check("SUBS-002-order-pending", "FR-SUBS-002", "order starts in a pending/unpaid state", st,
          st in ("PENDING", "PENDING_PAYMENT", "AWAITING_PAYMENT", "UNPAID"), f"status={st}")
    # ProductSnapshot frozen (DDD BC-08)
    snap = sql(f"select product_snapshot is not null from billing.purchase_order where id='{ORDER}'")
    check("SUBS-002-product-snapshot", "DDD Sec 5 BC-08 (ProductSnapshot)",
          "the order freezes a ProductSnapshot at creation", snap, snap == "t",
          f"snapshot present={snap}")

# ---------- FR-BILL-001 invoice generated ----------
if ORDER:
    r = biz.get(f"/orders/{ORDER}/invoice")
    check("BILL-001-invoice", "FR-BILL-001", "an invoice is produced with the order details", r,
          r.status_code == 200, r.text[:200])
    INVOICE = r.json().get("id") if r.status_code == 200 else None
else:
    INVOICE = None

# ---------- I-14 no entitlement before confirmed payment ----------
ents = biz.get("/me/entitlements")
n_before = len(ents.json().get("items", [])) if ents.status_code == 200 else 0
check("I-14-no-entitlement-before-payment", "I-14 / FR-SUBS-003",
      "no entitlement is active before payment is confirmed", ents,
      n_before == 0, f"{n_before} entitlements before confirmation")

# ---------- a non-operator cannot confirm payment ----------
if INVOICE:
    r = biz.post(f"/admin/billing/invoices/{INVOICE}/confirm-payment",
                 json={"paidAmount": {"amount": "100000", "currency": "UZS"},
                       "reference": "self-confirm"}, idem=True)
    check("BILL-002-self-confirm-denied", "FR-BILL-002 / NFR-SEC-002",
          "a buyer cannot confirm their own offline payment", r,
          r.status_code in (401, 403), r.text[:160])

# ---------- FR-BILL-002 operator confirms offline payment -> FR-SUBS-003 activation ----------
if INVOICE:
    r = admin.post(f"/admin/billing/invoices/{INVOICE}/confirm-payment",
                   json={"paidAmount": {"amount": "100000", "currency": "UZS"},
                         "reference": "OFFLINE-BANK-001"}, idem=True)
    check("BILL-002-confirm", "FR-BILL-002",
          "operator records confirmation of an offline payment", r,
          r.status_code in (200, 201, 204), r.text[:250])
    time.sleep(4)   # entitlement activation propagates via the outbox
    ents = biz.get("/me/entitlements")
    items = ents.json().get("items", []) if ents.status_code == 200 else []
    check("SUBS-003-entitlement-active", "FR-SUBS-003 / I-14",
          "on payment confirmation the entitlement becomes active", ents,
          len(items) > n_before, f"{len(items)} entitlements after confirmation")
    ostat = sql(f"select status from billing.purchase_order where id='{ORDER}'")
    check("BILL-002-order-paid", "FR-BILL-002", "confirmation updates the order to paid", ostat,
          ostat in ("PAID", "CONFIRMED", "COMPLETED"), f"order status={ostat}")

# ---------- FR-BILL-003 reconciliation visible in back office ----------
r = admin.get("/admin/billing/invoices")
check("BILL-003-admin-invoices", "FR-BILL-003",
      "invoice/payment status is visible and reconcilable in the back office", r,
      r.status_code == 200 and len(r.json().get("items", [])) > 0,
      f"{len(r.json().get('items', [])) if r.status_code == 200 else '-'} invoices")

# ---------- I-08 quota now that a SUBSCRIPTION entitlement (max_active_listings=2) is active ----
cats = httpx.get(f"{BASE}/categories").json()
K = next(c["id"] for c in cats if c["path"] == "/kvartira")
made, last = 0, None
for i in range(6):
    last = biz.post("/listings", json={
        "categoryId": K, "listingType": "ADVERTISEMENT", "title": f"Quota {i}",
        "description": "Kvota tekshiruvi", "attributes": {"rooms": 3, "area_m2": 50},
        "publish": True}, idem=True)
    if last.status_code in (200, 201):
        made += 1
    else:
        break
check("I-08-quota-enforced", "I-08 / FR-ADV-008 / BRULE-07",
      "listing creation beyond the plan quota (max_active_listings=2) is refused", last,
      made <= 2 and last.status_code in (403, 409),
      f"created {made} with a 2-listing plan; stopped at {last.status_code}")

ah.dump("/home/ameer/.claude/jobs/06393b27/tmp/res_billing.json")
