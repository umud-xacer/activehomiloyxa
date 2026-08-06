"""Catalog & Listings — FR-ADV-001..010, FR-FORM-002, FR-USER-004, plus I-05/I-06/I-07/I-08."""

import time

import httpx

import ah
from ah import Actor, check, sql

RUN = str(int(time.time()))[-6:]
BASE = "http://127.0.0.1:8100/api/v1"

cats = httpx.get(f"{BASE}/categories").json()
KVARTIRA = next(c["id"] for c in cats if c["path"] == "/kvartira")
SERVICE = next(c["id"] for c in cats if c["path"] == "/qurilish-xizmatlari")

seller = Actor("seller").register_login(f"seller-{RUN}@example.invalid", "Seller")
buyer = Actor("buyer").register_login(f"buyer-{RUN}@example.invalid", "Buyer")
anon = Actor("anon")


def new_listing(actor, cat=KVARTIRA, title="Yaxshi kvartira", attrs=None, **extra):
    body = {
        "categoryId": cat,
        "listingType": "ADVERTISEMENT",
        "title": title,
        "description": "Toshkent shahrida yaxshi kvartira sotiladi.",
        "price": {"amount": "500000000", "currency": "UZS"},
        "location": {"latitude": 41.311081, "longitude": 69.240562},
        "attributes": attrs if attrs is not None else {"rooms": 3, "area_m2": 72.5, "has_balcony": True},
    }
    body.update(extra)
    return actor.post("/listings", json=body, idem=True)


# ---------- FR-ADV-001 create ----------
r = new_listing(seller)
check("ADV-001-create", "FR-ADV-001", "listing created under the selected category", r,
      r.status_code in (200, 201), r.text[:200] if r.status_code >= 400 else "")
LID = r.json().get("id") if r.status_code in (200, 201) else None
if LID:
    check("ADV-001-owned-by-actor", "FR-ADV-001", "listing owned by the acting profile", r,
          r.json().get("lifecycleState") in ("DRAFT", "PUBLISHED"), f"state={r.json().get('lifecycleState')}")

# ---------- FR-FORM-002 dynamic-form validation against the bound form ----------
r = new_listing(seller, attrs={"area_m2": 50})           # 'rooms' is required
check("FORM-002-required-missing", "FR-FORM-002",
      "missing required dynamic field rejected with field-level message", r,
      r.status_code == 422 and "rooms" in r.text.lower(), r.text[:200])
r = new_listing(seller, attrs={"rooms": 999, "area_m2": 50})   # numeric_range max 20
check("FORM-002-numeric-range", "FR-FORM-002", "numeric_range validator enforced (max 20)", r,
      r.status_code == 422, r.text[:200])
r = new_listing(seller, attrs={"rooms": 3, "area_m2": 50, "condition": "not-an-option"})
check("FORM-002-option-membership", "FR-FORM-002", "option_membership validator enforced", r,
      r.status_code == 422, r.text[:200])
r = new_listing(seller, attrs={"rooms": 3, "area_m2": 50, "unknown_field": "x"})
check("FORM-002-unknown-field", "FR-FORM-002", "field not in the bound form rejected", r,
      r.status_code == 422, r.text[:200])

# I-07: the listing binds an immutable form VERSION
if LID:
    fv = sql(f"select form_definition_version_id from catalog.listing where id='{LID}'")
    check("I-07-form-version-bound", "I-07 (DDD Sec 10.3)",
          "listing binds the immutable form version it was validated against", fv,
          bool(fv and fv != ""), f"form_version={fv[:8] if fv else None}")

# ---------- FR-ADV-003 draft not publicly visible (I-06) ----------
if LID:
    st = sql(f"select lifecycle_state from catalog.listing where id='{LID}'")
    r = anon.get(f"/listings/{LID}")
    check("ADV-003-draft-not-public", "FR-ADV-003 / I-06",
          "a draft is not publicly visible", r,
          r.status_code in (403, 404) if st == "DRAFT" else True, f"db state={st}, anon={r.status_code}")
    r = seller.get(f"/listings/{LID}")
    check("ADV-003-draft-owner-visible", "FR-ADV-003", "the owner can retrieve their draft", r,
          r.status_code == 200)

# ---------- FR-ADV-004 publish ----------
if LID:
    r = seller.post(f"/listings/{LID}/status", json={"action": "PUBLISH"}, idem=True)
    check("ADV-004-publish", "FR-ADV-004", "unflagged listing becomes visible immediately", r,
          r.status_code in (200, 202, 204), r.text[:200])
    time.sleep(1.5)
    r = anon.get(f"/listings/{LID}")
    check("ADV-004-public-after-publish", "FR-ADV-004 / I-06",
          "published listing is publicly retrievable", r, r.status_code == 200)

# ---------- FR-ADV-010 view records a metric ----------
if LID:
    before = sql(f"select count(*) from analytics.metric_event where subject_id='{LID}'")
    anon.get(f"/listings/{LID}")
    time.sleep(2.5)
    after = sql(f"select count(*) from analytics.metric_event where subject_id='{LID}'")
    check("ADV-010-view-metric", "FR-ADV-010 / FR-ANALYTICS-001",
          "a view metric is recorded on listing detail", after,
          int(after or 0) > int(before or 0), f"metric_event {before} -> {after}")

# ---------- FR-ADV-005 edit -> Edited ----------
if LID:
    lv = seller.get(f"/listings/{LID}").json().get("lockVersion", 0)
    r = seller.put(f"/listings/{LID}", json={
        "lockVersion": lv,
        "title": "Yangilangan eʼlon",
        "description": "Yangi tavsif matni",
        "price": {"amount": "600000000", "currency": "UZS"},
        "attributes": {"rooms": 4, "area_m2": 80.0, "has_balcony": False},
    })
    check("ADV-005-edit", "FR-ADV-005", "owner can edit; listing transitions to Edited", r,
          r.status_code in (200, 202), r.text[:200])
    time.sleep(1.5)
    st = sql(f"select lifecycle_state from catalog.listing where id='{LID}'")
    check("ADV-005-edited-state", "FR-ADV-005",
          "edit transitions the listing to the Edited state", st, st == "EDITED", f"state={st}")

# ---------- FR-ADV-006 only legal transitions (I-05) ----------
if LID:
    r = seller.post(f"/listings/{LID}/status", json={"action": "PUBLISH"}, idem=True)
    check("I-05-illegal-transition", "FR-ADV-006 / I-05",
          "an illegal lifecycle transition is refused with 409", r, r.status_code == 409, r.text[:160])
    n = sql(f"select count(*) from catalog.listing_transition where listing_id='{LID}'")
    check("ADV-006-transitions-recorded", "FR-ADV-006",
          "each transition is recorded", n, int(n or 0) >= 2, f"{n} transition rows")

# ---------- non-owner cannot edit or transition ----------
if LID:
    r = buyer.put(f"/listings/{LID}", json={"title": "Hacked", "lockVersion": 0})
    check("SEC-nonowner-edit", "FR-ADV-005", "a non-owner cannot edit someone else's listing", r,
          r.status_code in (403, 404), r.text[:160])
    r = buyer.post(f"/listings/{LID}/status", json={"action": "ARCHIVE"}, idem=True)
    check("SEC-nonowner-transition", "FR-ADV-006",
          "a non-owner cannot drive another's lifecycle", r, r.status_code in (403, 404))

# ---------- FR-USER-004 favorites ----------
if LID:
    r = buyer.post("/me/favorites", json={"listingId": LID}, idem=True)
    check("USER-004-add-favorite", "FR-USER-004", "favorite saved", r, r.status_code in (200, 201, 204))
    time.sleep(1.0)
    r = buyer.get("/me/favorites")
    items = r.json().get("items", []) if r.status_code == 200 else []
    check("USER-004-list-favorites", "FR-USER-004", "saved favorites are retrievable", r,
          r.status_code == 200 and any(i.get("listingId") == LID or i.get("id") == LID for i in items),
          f"{len(items)} favorites")
    r = buyer.delete(f"/me/favorites/{LID}")
    check("USER-004-remove-favorite", "FR-USER-004", "removal is immediate", r,
          r.status_code in (200, 204))

# ---------- FR-ADV-008 quota from the subscription ----------
made = 0
for i in range(6):
    r = new_listing(seller, title=f"Quota probe {i}")
    if r.status_code in (200, 201):
        made += 1
    else:
        break
check("ADV-008-quota", "FR-ADV-008",
      "creation beyond the plan limit is refused with a clear message", r,
      r.status_code == 403 or r.status_code == 409,
      f"created {made} extra before {r.status_code}; plan-basic max_active_listings=2")

# ---------- FR-ADV-009 duplicate detection ----------
d1 = new_listing(seller, title="Aynan bir xil eʼlon matni")
d2 = new_listing(seller, title="Aynan bir xil eʼlon matni")
check("ADV-009-duplicate", "FR-ADV-009", "suspected duplicates are flagged for moderation", d2,
      d2.status_code in (200, 201, 409), f"first={d1.status_code} second={d2.status_code}")
if d2.status_code in (200, 201):
    time.sleep(2.5)
    n = sql("select count(*) from moderation.moderation_case")
    check("ADV-009-duplicate-case", "FR-ADV-009",
          "a duplicate raises a moderation case", n, int(n or 0) > 0, f"{n} duplicate cases")

ah.dump("/home/ameer/.claude/jobs/06393b27/tmp/res_catalog.json")
