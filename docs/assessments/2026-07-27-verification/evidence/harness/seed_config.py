"""Author the eight configuration entities through the real admin API (FR-CFG-001..005).

Everything goes through /admin/config/* — nothing inserted directly — so this doubles as the
configuration-authoring verification (Head+Version, validate, maker–checker publish).
"""

import json
import sys

import httpx

BASE = "http://127.0.0.1:8100/api/v1"
TOKENS = open("/home/ameer/.claude/jobs/06393b27/tmp/admin_tokens.txt").read().split()


def cli(tok):
    return httpx.Client(
        base_url=BASE, timeout=60, headers={"Authorization": f"Bearer {tok}"},
        limits=httpx.Limits(max_keepalive_connections=0),
    )


maker, checker = cli(TOKENS[0]), cli(TOKENS[1])
OUT = {}


def lt(uz, cy, ru, en):
    return {"uz_latn": uz, "uz_cyrl": cy, "ru": ru, "en": en}


def desc(name, order=0):
    return {"name": name, "display_order": order, "metadata": {}}


def author(entity: str, code: str, definition: dict, owner: str = "Verification") -> dict:
    r = maker.post(
        f"/admin/config/{entity}",
        json={"code": code, "businessOwner": owner, "definition": definition},
    )
    if r.status_code == 409:
        # Head already exists -> author a NEW VERSION on it (createConfigVersionDraft).
        heads = maker.get(f"/admin/config/{entity}").json()
        head = next(
            (h["id"] for h in heads.get("items", []) if h.get("code") == code), None
        )
        if head is None:
            print(f"  !! {entity}/{code}: 409 but head not found in listConfigHeads")
            return {}
        r = maker.post(
            f"/admin/config/{entity}/{head}/versions", json={"definition": definition}
        )
        if r.status_code not in (200, 201):
            print(f"  !! new version {entity}/{code} -> {r.status_code} {r.text[:250]}")
            return {}
        ver = r.json()["id"]
    elif r.status_code not in (200, 201):
        print(f"  !! create {entity}/{code} -> {r.status_code} {r.text[:250]}")
        return {}
    else:
        v = r.json()
        head, ver = v["headId"], v["id"]
    val = maker.post(f"/admin/config/{entity}/{head}/versions/{ver}/validate")
    valid = val.json().get("valid") if val.status_code == 200 else None
    if valid is False:
        print(f"  !! validate {entity}/{code} invalid: {json.dumps(val.json()['errors'])[:400]}")
    # publishConfigVersion drives BOTH transitions: DRAFT -> APPROVAL -> PUBLISHED, so it must
    # be called twice (Config Framework Sec 2.3 documents approve and publish as separate steps).
    for _ in range(2):
        pub = checker.post(
            f"/admin/config/{entity}/{head}/versions/{ver}/publish",
            json={"approvalNote": "verification run"},
        )
        if pub.status_code not in (200, 201, 204):
            break
        if pub.json().get("status") == "PUBLISHED":
            break
    ok = pub.status_code in (200, 201, 204) and pub.json().get("status") == "PUBLISHED"
    print(f"  {entity}/{code}: validate.valid={valid} publish={pub.status_code}"
          + ("" if ok else f" {pub.text[:250]}"))
    return {"head": head, "version": ver, "publish": pub.status_code, "valid": valid, "ok": ok}


print("== form-definitions ==")
apartment_form = {
    "descriptor": desc(lt("Kvartira shakli", "Квартира шакли", "Форма квартиры", "Apartment form")),
    "sections": [{"code": "main", "label": lt("Asosiy", "Асосий", "Основное", "Main"), "order": 1}],
    "fields": [
        {"code": "rooms", "section_code": "main",
         "label": lt("Xonalar", "Хоналар", "Комнаты", "Rooms"),
         "field_type": "number", "required": True, "facet_eligible": True, "order": 1,
         "validators": [{"validator_type": "required", "params": {}},
                        {"validator_type": "numeric_range", "params": {"min": 1, "max": 20}}]},
        {"code": "area_m2", "section_code": "main",
         "label": lt("Maydon", "Майдон", "Площадь", "Area m2"),
         "field_type": "number", "required": True, "facet_eligible": True, "order": 2,
         "validators": [{"validator_type": "numeric_range", "params": {"min": 1, "max": 10000}}]},
        {"code": "has_balcony", "section_code": "main",
         "label": lt("Balkon", "Балкон", "Балкон", "Balcony"),
         "field_type": "boolean", "required": False, "facet_eligible": True, "order": 3},
        {"code": "condition", "section_code": "main",
         "label": lt("Holati", "Ҳолати", "Состояние", "Condition"),
         "field_type": "select", "required": False, "facet_eligible": True, "order": 4,
         "options": [{"value": "new", "label": lt("Yangi", "Янги", "Новый", "New")},
                     {"value": "used", "label": lt("Ishlatilgan", "Ишлатилган", "Б/у", "Used")}],
         "validators": [{"validator_type": "option_membership", "params": {}}]},
    ],
}
service_form = {
    "descriptor": desc(lt("Xizmat shakli", "Хизмат шакли", "Форма услуги", "Service form")),
    "sections": [{"code": "main", "label": lt("Xizmat", "Хизмат", "Услуга", "Service"), "order": 1}],
    "fields": [
        {"code": "experience_years", "section_code": "main",
         "label": lt("Tajriba", "Тажриба", "Опыт", "Experience"),
         "field_type": "number", "required": True, "facet_eligible": True, "order": 1,
         "validators": [{"validator_type": "required", "params": {}}]},
    ],
}
OUT["form_apartment"] = author("form-definition", "form-apartment", apartment_form)
OUT["form_service"] = author("form-definition", "form-service", service_form)

print("== categories ==")
cats = [
    ("kvartira", lt("Kvartira", "Квартира", "Квартира", "Apartment"), "form_apartment"),
    ("qurilish-xizmatlari", lt("Qurilish xizmatlari", "Қурилиш хизматлари",
                               "Строительные услуги", "Construction services"), "form_service"),
    ("gisht", lt("Gʻisht", "Ғишт", "Кирпич", "Brick"), "form_apartment"),
]
for i, (code, name, form) in enumerate(cats):
    if not OUT.get(form, {}).get("ok"):
        print(f"  -- skip category/{code}: its form did not publish")
        continue
    OUT[f"cat_{code}"] = author("category", code, {
        "descriptor": desc(name, i),
        "path": f"/{code}",
        "form_definition_id": OUT[form]["head"],
        "tree_status": "ACTIVE",
    })

print("== product-definitions (all six PRODUCT_TYPEs, FR-SUBS-001) ==")
for code, ptype, price, quota in [
    ("plan-basic", "SUBSCRIPTION", "100000", {"max_active_listings": 2, "promotion_credits": 0}),
    ("promo-premium", "PREMIUM", "50000", None),
    ("promo-featured", "FEATURED", "40000", None),
    ("promo-top", "TOP_PLACEMENT", "60000", None),
    ("verification-standard", "VERIFICATION", "200000", None),
    ("banner-home-hero", "BANNER_PLACEMENT", "300000", None),
]:
    body = {"descriptor": desc(lt(code, code, code, code)), "product_type": ptype,
            "price_amount": price, "price_currency": "UZS", "term_days": 30,
            "benefit_descriptor": {}}
    if quota:
        body["quota_set"] = quota
    OUT[code] = author("product-definition", code, body)

print("== placement-slot ==")
OUT["slot"] = author("placement-slot", "home-hero", {
    "descriptor": desc(lt("Bosh sahifa", "Бош саҳифа", "Главная", "Home hero")),
    "slot_key": "home-hero", "page_zone": "HOMEPAGE_HERO",
    "width_px": 1200, "height_px": 300, "targeting_dimensions": ["category", "geo", "language"]})

print("== search-configuration ==")
OUT["searchcfg"] = author("search-configuration", "default-search", {
    "descriptor": desc(lt("Qidiruv", "Қидирув", "Поиск", "Search")),
    "facets": [
        {"field_code": "rooms", "label": lt("Xonalar", "Хоналар", "Комнаты", "Rooms"), "order": 1},
        {"field_code": "condition", "label": lt("Holati", "Ҳолати", "Состояние", "Condition"), "order": 2},
    ],
    "sort_options": ["RELEVANCE", "NEWEST", "PRICE_ASC", "PRICE_DESC"],
    "default_sort": "RELEVANCE", "promotion_page_cap": 3})

print("== notification-template ==")
for code, ek, ch in [("listing-published-email", "ListingPublished", "EMAIL"),
                     ("message-sent-email", "MessageSent", "EMAIL")]:
    OUT[code] = author("notification-template", code, {
        "descriptor": desc(lt(code, code, code, code)),
        "event_key": ek, "channel": ch,
        "subject": lt("Eʼlon chop etildi", "Эълон чоп этилди", "Опубликовано", "Published"),
        "body": lt("Eʼloningiz chop etildi.", "Эълонингиз чоп этилди.",
                   "Ваше объявление опубликовано.", "Your listing is published.")})

print("== role-definition (operator roles) ==")
for code, name, perms in [
    ("moderator", "Moderator", ["moderation:case:review", "catalog:listing:moderate", "profiles:profile:moderate"]),
    ("verification-reviewer", "Verification Reviewer", ["profiles:verification:review"]),
    ("billing-ops", "Billing Ops", ["billing:invoice:confirm_payment"]),
]:
    OUT[code] = author("role-definition", code, {
        "descriptor": desc(lt(name, name, name, name)),
        "role_name": name, "permission_keys": perms,
        "permission_group_codes": [], "parent_role_code": None})

json.dump(OUT, open("/home/ameer/.claude/jobs/06393b27/tmp/config_ids.json", "w"), indent=1)
ok = sum(1 for v in OUT.values() if v.get("ok"))
print(f"\n{ok}/{len(OUT)} configuration entities published", file=sys.stderr)
