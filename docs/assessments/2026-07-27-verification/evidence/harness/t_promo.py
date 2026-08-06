"""FR-SRCH-005 paid ranking: promoted listings are labelled and capped; degraded flag."""

import subprocess
import time

import httpx

import ah
from ah import Actor, check, items, sql

RUN = str(int(time.time()))[-6:]
BASE = "http://127.0.0.1:8100/api/v1"
TOK = open("/home/ameer/.claude/jobs/06393b27/tmp/admin_tokens.txt").read().split()
admin = Actor("admin")
admin.c.headers["Authorization"] = f"Bearer {TOK[0]}"
anon = Actor("anon")

prods = httpx.get(f"{BASE}/products").json()
PREMIUM = next(p["id"] for p in prods if p["productType"] == "PREMIUM")
PLAN = next(p["id"] for p in prods if p["productType"] == "SUBSCRIPTION")
cats = httpx.get(f"{BASE}/categories").json()
K = next(c["id"] for c in cats if c["path"] == "/kvartira")

biz = Actor("promo").register_login(f"promo-{RUN}@example.invalid", "Promo Biz")
PID = biz.post("/business-profiles", json={
    "profileType": "SUPPLIER", "name": {"uz_latn": "Promo", "ru": "Promo", "en": "Promo"}},
    idem=True).json()["id"]
time.sleep(4)
biz.post("/me/sessions/switch-profile", json={"actingProfileId": PID})


def pay(product, target_type="PROFILE", target_id=None):
    body = {"productId": product, "targetType": target_type}
    if target_id:
        body["targetId"] = target_id
    o = biz.post("/orders", json=body, idem=True)
    if o.status_code not in (200, 201):
        return None, o
    inv = biz.get(f"/orders/{o.json()['id']}/invoice").json()["id"]
    c = admin.post(f"/admin/billing/invoices/{inv}/confirm-payment",
                   json={"confirmed": True, "note": "promo"}, idem=True)
    return o.json()["id"], c


pay(PLAN)
time.sleep(4)

r = biz.post("/listings", json={
    "categoryId": K, "listingType": "ADVERTISEMENT", "title": f"Reklama kvartira {RUN}",
    "description": "Promotsiya sinovi uchun eʼlon", "price": {"amount": "1000", "currency": "UZS"},
    "location": {"latitude": 41.311, "longitude": 69.240},
    "attributes": {"rooms": 3, "area_m2": 60}, "publish": True}, idem=True)
LID = r.json()["id"] if r.status_code in (200, 201) else None
check("PROMO-listing", "test setup", "a listing to promote is published", r,
      LID is not None, r.text[:200])

if LID:
    _, conf = pay(PREMIUM, "LISTING", LID)
    check("SRCH-005-promotion-purchase", "FR-SUBS-002 / FR-SRCH-005",
          "a PREMIUM promotion can be purchased for a listing and confirmed", conf,
          conf is not None and conf.status_code in (200, 201, 204),
          conf.text[:200] if conf is not None else "order refused")
    time.sleep(10)   # entitlement -> catalog promotion marker -> search reindex
    pk = sql(f"select promotion_kind from catalog.listing where id='{LID}'")
    check("SRCH-005-promotion-marker", "DDD BC-03 PromotionApplicationPolicy",
          "EntitlementActivated applies a PromotionMarker to the listing", pk,
          pk == "PREMIUM", f"promotion_kind={pk!r}")

    r = anon.get("/search", params={"q": f"Reklama kvartira {RUN}"})
    hits = items(r)
    mine = next((h for h in hits if h.get("listingId") == LID), None)
    check("SRCH-005-labelled", "FR-SRCH-005 / BRULE-10",
          "a promoted result is clearly labelled in the search response", mine,
          mine is not None and isinstance(mine.get("promoted"), dict)
          and mine["promoted"].get("kind") == "PREMIUM",
          f"promoted={mine.get('promoted') if mine else 'hit not found'}")

    r = anon.get("/search")
    hits = items(r)
    promoted = [h for h in hits if h.get("promoted")]
    check("SRCH-005-cap", "FR-SRCH-005 / BRULE-10 (promotion_page_cap = 3)",
          "promoted results do not exceed the configured per-page cap", promoted,
          len(promoted) <= 3, f"{len(promoted)} promoted of {len(hits)} on the page")

# ---------- degraded flag on the documented fallback path ----------
subprocess.run(["docker", "stop", "ahv-opensearch"], capture_output=True)
time.sleep(3)
r = anon.get("/search", params={"q": "kvartira"})
body = r.json() if r.status_code == 200 else {}
check("DEGRADE-flag", "contracts SearchResult.degraded "
      "('True when served from the DB fallback')",
      "the response marks itself degraded while OpenSearch is down", body,
      isinstance(body, dict) and body.get("degraded") is True,
      f"degraded={body.get('degraded') if isinstance(body, dict) else 'n/a'}, "
      f"hits={len(items(r))}")
subprocess.run(["docker", "start", "ahv-opensearch"], capture_output=True)
for _ in range(40):
    time.sleep(2)
    try:
        if httpx.get("http://localhost:9201/_cluster/health", timeout=5).status_code == 200:
            break
    except Exception:  # noqa: BLE001
        pass
time.sleep(3)
r = anon.get("/search", params={"q": "kvartira"})
b = r.json()
check("DEGRADE-flag-clear", "contracts SearchResult.degraded",
      "degraded returns to false once OpenSearch recovers", b,
      isinstance(b, dict) and b.get("degraded") is False and len(items(r)) > 0,
      f"degraded={b.get('degraded') if isinstance(b, dict) else 'n/a'} hits={len(items(r))}")

ah.dump("/home/ameer/.claude/jobs/06393b27/tmp/res_promo.json")
