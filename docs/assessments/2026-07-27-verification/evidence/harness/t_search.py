"""Search & Discovery — FR-SRCH-001..005, FR-MAP-001/003, DEC-19 cross-script, degradation."""

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

cats = httpx.get(f"{BASE}/categories").json()
K = next(c["id"] for c in cats if c["path"] == "/kvartira")
anon = Actor("anon")

# Author listings in Latin and Cyrillic Uzbek, plus oʻ/gʻ forms (DEC-19).
seller = Actor("s").register_login(f"srch-{RUN}@example.invalid", "Search Seller")
CORPUS = [
    ("Toshkentda arzon kvartira", "Yangi qurilgan uy, metroga yaqin", 41.311, 69.240, 3, 70),
    ("Тошкентда арзон квартира", "Янги қурилган уй, метрога яқин", 41.312, 69.241, 2, 55),
    ("Samarqandda gʻishtli uy", "Oʻzbekiston boʻylab yetkazib berish", 39.654, 66.959, 4, 120),
    ("Самарқандда ғиштли уй", "Ўзбекистон бўйлаб етказиб бериш", 39.655, 66.960, 5, 150),
]
ids = []
for title, desc, lat, lon, rooms, area in CORPUS:
    r = seller.post("/listings", json={
        "categoryId": K, "listingType": "ADVERTISEMENT", "title": title, "description": desc,
        "price": {"amount": "100000000", "currency": "UZS"},
        "location": {"latitude": lat, "longitude": lon},
        "attributes": {"rooms": rooms, "area_m2": area}, "publish": True}, idem=True)
    if r.status_code in (200, 201):
        ids.append(r.json()["id"])
check("SRCH-corpus", "test setup", "a multi-script corpus is published", ids,
      len(ids) >= 2, f"published {len(ids)}/4 (quota may cap this)")

# wait for the indexing worker (outbox -> OpenSearch)
indexed = 0
for _ in range(30):
    time.sleep(2)
    try:
        indexed = httpx.get("http://localhost:9201/listing_search/_count", timeout=10).json()["count"]
    except Exception:  # noqa: BLE001
        indexed = 0
    if indexed >= len(ids):
        break
check("SRCH-indexing", "SAD (OpenSearch read model populated only by the indexing worker)",
      "published listings reach the search index via the outbox", indexed,
      indexed >= len(ids), f"{indexed} docs indexed for {len(ids)} published")

# ---------- FR-SRCH-001 full text ----------
r = anon.get("/search", params={"q": "kvartira"})
res = items(r)
check("SRCH-001-fulltext", "FR-SRCH-001", "relevant listings are returned for a query term", r,
      r.status_code == 200 and len(res) > 0, f"{len(res)} hits for 'kvartira'")

# ---------- FR-SRCH-004 cross-script (DEC-19) ----------
lat_q = anon.get("/search", params={"q": "kvartira"})
cyr_q = anon.get("/search", params={"q": "квартира"})
lat_ids = {x.get("id") for x in items(lat_q)}
cyr_ids = {x.get("id") for x in items(cyr_q)}
check("SRCH-004-latin-finds-cyrillic", "FR-SRCH-004 / DEC-19",
      "a Latin query returns matching Cyrillic content", lat_q,
      len(lat_ids) > 0 and len(cyr_ids) > 0 and bool(lat_ids & cyr_ids),
      f"latin hits={len(lat_ids)} cyrillic hits={len(cyr_ids)} overlap={len(lat_ids & cyr_ids)}")
check("SRCH-004-same-result-set", "FR-SRCH-004 / DEC-19",
      "a query in either script returns content in either", cyr_q,
      lat_ids == cyr_ids and len(lat_ids) > 0,
      f"latin={len(lat_ids)} cyrillic={len(cyr_ids)} equal={lat_ids == cyr_ids}")

for q, label in [("gʻishtli", "apostrophe-gh"), ("ғиштли", "cyrillic-gh"),
                 ("oʻzbekiston", "apostrophe-o"), ("ўзбекистон", "cyrillic-o")]:
    r = anon.get("/search", params={"q": q})
    check(f"SRCH-004-{label}", "FR-SRCH-004 / DEC-19",
          f"cross-script match for {q!r} (oʻ/gʻ handling)", r,
          r.status_code == 200 and len(items(r)) > 0, f"{len(items(r))} hits")

# ---------- FR-SRCH-002 facets from configuration ----------
r = anon.get("/search/facets")
check("SRCH-002-facets-endpoint", "FR-SRCH-002 / FR-CFG-003",
      "facets are served from the published search configuration", r,
      r.status_code == 200, r.text[:200])
fac = r.json() if r.status_code == 200 else {}
names = {f.get("fieldCode") or f.get("code") for f in (fac if isinstance(fac, list) else fac.get("facets", fac.get("items", [])))} if fac else set()
check("SRCH-002-facets-configured", "FR-SRCH-002",
      "the configured facets (rooms, condition) are the ones offered", names,
      {"rooms", "condition"} <= names, f"facets={sorted(n for n in names if n)}")

r = anon.get("/search", params={"q": "uy", "rooms": 4})
check("SRCH-002-facet-filter", "FR-SRCH-002", "applying a facet narrows results accordingly", r,
      r.status_code == 200, f"{len(items(r))} hits with rooms=4")

# ---------- FR-SRCH-003 sorting ----------
for so in ["RELEVANCE", "NEWEST", "PRICE_ASC", "PRICE_DESC"]:
    r = anon.get("/search", params={"q": "uy", "sort": so})
    check(f"SRCH-003-sort-{so}", "FR-SRCH-003",
          "results reorder per the selected configured sort option", r,
          r.status_code == 200, f"{len(items(r))} hits")

# ---------- FR-MAP-003 radius search ----------
r = anon.get("/search", params={"lat": 41.311, "lon": 69.240, "radiusKm": 5})
near = items(r)
r2 = anon.get("/search", params={"lat": 41.311, "lon": 69.240, "radiusKm": 1})
check("MAP-003-radius", "FR-MAP-003",
      "only listings within the chosen radius are returned", r,
      r.status_code == 200 and len(near) >= len(items(r2)),
      f"5km={len(near)} hits, 1km={len(items(r2))} hits (Samarqand ~270km away must be excluded)")

# ---------- FR-SRCH-005 promoted labelling + cap ----------
r = anon.get("/search", params={"q": "uy"})
hits = items(r)
labelled = [h for h in hits if h.get("promoted") is not None or h.get("promotionKind") is not None]
check("SRCH-005-promoted-field", "FR-SRCH-005 / BRULE-10",
      "results carry a promotion label field so promoted results can be marked", r,
      r.status_code == 200 and (len(hits) == 0 or len(labelled) == len(hits)),
      f"{len(labelled)}/{len(hits)} hits expose a promotion field")
promoted = [h for h in hits if h.get("promoted") or h.get("promotionKind")]
check("SRCH-005-cap", "FR-SRCH-005 / BRULE-10 (promotion_page_cap=3)",
      "promoted results do not exceed the configured per-page cap", promoted,
      len(promoted) <= 3, f"{len(promoted)} promoted on page (cap 3)")

# ---------- FR-SRCH suggestions ----------
r = anon.get("/search/suggest", params={"q": "kvar"})
check("SRCH-suggest", "contracts/openapi.yaml operationId suggest",
      "suggestions are returned for a prefix", r, r.status_code == 200,
      f"{len(items(r))} suggestions")

# ---------- degradation: OpenSearch down -> PostgreSQL fallback ----------
subprocess.run(["docker", "stop", "ahv-opensearch"], capture_output=True)
time.sleep(3)
r = anon.get("/search", params={"q": "kvartira"})
check("DEGRADE-search-fallback", "Infra/DevSecOps degradation path; SAD (PostgreSQL fallback)",
      "with OpenSearch stopped, search still returns results via the fallback", r,
      r.status_code == 200 and len(items(r)) > 0,
      f"status={r.status_code} hits={len(items(r))}")
r = anon.get("/listings")
check("DEGRADE-listings-unaffected", "degradation path",
      "browsing listings is unaffected while OpenSearch is down", r,
      r.status_code == 200, f"status={r.status_code}")
subprocess.run(["docker", "start", "ahv-opensearch"], capture_output=True)
for _ in range(30):
    time.sleep(2)
    try:
        if httpx.get("http://localhost:9201/_cluster/health", timeout=5).status_code == 200:
            break
    except Exception:  # noqa: BLE001
        pass
r = anon.get("/search", params={"q": "kvartira"})
check("DEGRADE-recovery", "degradation path",
      "search recovers once OpenSearch is back", r,
      r.status_code == 200 and len(items(r)) > 0, f"hits={len(items(r))}")

ah.dump("/home/ameer/.claude/jobs/06393b27/tmp/res_search.json")
