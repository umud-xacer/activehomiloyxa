"""Messaging & Contact — FR-MSG-001..005, I-18, I-19, plus realtime WSS delivery."""

import asyncio
import json
import time

import httpx
import websockets

import ah
from ah import Actor, check, items, sql

RUN = str(int(time.time()))[-6:]
BASE = "http://127.0.0.1:8100/api/v1"
WS = "ws://127.0.0.1:8101/ws/messaging"
cats = httpx.get(f"{BASE}/categories").json()
K = next(c["id"] for c in cats if c["path"] == "/kvartira")

seller = Actor("seller").register_login(f"msg-s-{RUN}@example.invalid", "Msg Seller")
buyer = Actor("buyer").register_login(f"msg-b-{RUN}@example.invalid", "Msg Buyer")
third = Actor("third").register_login(f"msg-t-{RUN}@example.invalid", "Third Party")

r = seller.post("/listings", json={
    "categoryId": K, "listingType": "ADVERTISEMENT", "title": f"Chat uchun eʼlon {RUN}",
    "description": "Suhbat sinovi", "price": {"amount": "5000", "currency": "UZS"},
    "attributes": {"rooms": 2, "area_m2": 45}, "publish": True}, idem=True)
LID = r.json()["id"] if r.status_code in (200, 201) else None
check("MSG-setup", "test setup", "a published listing to chat about", r, LID is not None,
      r.text[:200])

# ---------- FR-MSG-001 initiate chat ----------
CONV = None
if LID:
    # messaging keeps its own projection of listing owners (fed by catalog events); allow it
    # to catch up before judging.
    for _ in range(20):
        r = buyer.post("/conversations",
                       json={"listingId": LID, "message": "Salom! Eʼlon hali dolzarbmi?"},
                       idem=True)
        if r.status_code != 503:
            break
        time.sleep(2)
    check("MSG-001-initiate", "FR-MSG-001", "a conversation is created for the listing", r,
          r.status_code in (200, 201), r.text[:250])
    CONV = r.json().get("id") if r.status_code in (200, 201) else None
    time.sleep(3)
    n = sql("select count(*) from analytics.metric_event where metric_key ilike '%chat%'")
    check("MSG-001-metric", "FR-MSG-001 / FR-ANALYTICS-001 (ChatInitiated)",
          "a chat-initiation metric is recorded (DEC-06)", n, int(n or 0) > 0,
          f"{n} chat metric rows")

# ---------- FR-MSG-002 persistence + I-19 two participants ----------
if CONV:
    r = buyer.post(f"/conversations/{CONV}/messages",
                   json={"body": "Assalomu alaykum, narxi kelishiladimi?"}, idem=True)
    check("MSG-002-send", "FR-MSG-002", "a message is accepted", r,
          r.status_code in (200, 201), r.text[:200])
    time.sleep(1)
    r = seller.get(f"/conversations/{CONV}/messages")
    msgs = items(r)
    check("MSG-002-persist", "FR-MSG-002",
          "conversation history persists and is readable by the other participant", r,
          r.status_code == 200 and len(msgs) > 0, f"{len(msgs)} messages")

    # I-19: exactly two participants — a third party cannot read or post
    r = third.get(f"/conversations/{CONV}/messages")
    check("I-19-third-party-read", "I-19 / FR-MSG-002",
          "a third party cannot read a two-party conversation", r,
          r.status_code in (403, 404), r.text[:160])
    r = third.post(f"/conversations/{CONV}/messages", json={"body": "Men kimman?"}, idem=True)
    check("I-19-third-party-write", "I-19",
          "a third party cannot post into a two-party conversation", r,
          r.status_code in (403, 404), r.text[:160])

# ---------- FR-MSG-002 realtime delivery over WSS ----------
async def ws_roundtrip():
    tok = seller.c.headers["Authorization"].split()[1]
    try:
        async with websockets.connect(WS, additional_headers={"Authorization": f"Bearer {tok}"},
                                      open_timeout=10) as sock:
            await asyncio.sleep(0.5)
            buyer.post(f"/conversations/{CONV}/messages",
                       json={"body": f"Realtime sinov {RUN}"}, idem=True)
            raw = await asyncio.wait_for(sock.recv(), timeout=15)
            return True, raw[:300]
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


if CONV:
    ok, detail = asyncio.run(ws_roundtrip())
    check("MSG-002-realtime-wss", "FR-MSG-002 / DEC-11",
          "messages are delivered to the other participant in real time over WSS", detail,
          ok, str(detail)[:250])

    # unauthenticated WS must be refused
    async def ws_anon():
        try:
            async with websockets.connect(WS, open_timeout=8):
                return False, "connection accepted without credentials"
        except Exception as exc:  # noqa: BLE001
            return True, f"{type(exc).__name__}"

    ok, detail = asyncio.run(ws_anon())
    check("MSG-002-wss-auth", "Security Arch (session auth on the realtime gateway)",
          "an unauthenticated WSS upgrade is refused", detail, ok, str(detail)[:160])

# ---------- FR-MSG-003 phone reveal gated by privacy settings (I-18, BRULE-13) ----------
# Email-registered accounts hold no phone number, and there is no API to add one without a
# real Eskiz OTP, so the seller's phone is seeded directly for this check only.
sql(f"update identity.user_account set phone='+998901112233' "
    f"where id='{seller.user_id}'")
if CONV:
    seller.put("/me/preferences", json={"privacySettings": {"phoneRevealMode": "NEVER"}})
    time.sleep(2)
    r = buyer.post(f"/conversations/{CONV}/phone-reveal", idem=True)
    check("I-18-reveal-refused", "FR-MSG-003 / I-18 / BRULE-13",
          "phone is NOT revealed when the owner's setting forbids it", r,
          r.status_code in (403, 404, 409), f"{r.status_code} {r.text[:160]}")
    seller.put("/me/preferences", json={"privacySettings": {"phoneRevealMode": "ON_REQUEST"}})
    time.sleep(2)
    r = buyer.post(f"/conversations/{CONV}/phone-reveal", idem=True)
    check("I-18-reveal-permitted", "FR-MSG-003 / I-18",
          "phone IS revealed when the owner's setting permits it", r,
          r.status_code in (200, 201), f"{r.status_code} {r.text[:160]}")
    time.sleep(3)
    n = sql("select count(*) from analytics.metric_event where metric_key ilike '%phone%'")
    check("MSG-003-metric", "FR-MSG-003 / FR-ANALYTICS-001 (PhoneRevealed)",
          "a phone-reveal metric is recorded", n, int(n or 0) > 0, f"{n} phone-reveal metrics")

# ---------- FR-MSG-004 block (I-19) ----------
if CONV:
    r = seller.post("/me/blocks", json={"blockedUserId": buyer.user_id}, idem=True)
    check("MSG-004-block", "FR-MSG-004", "a user can block another user", r,
          r.status_code in (200, 201, 204), r.text[:200])
    time.sleep(2)
    r = buyer.post(f"/conversations/{CONV}/messages",
                   json={"body": "Bloklangandan keyin"}, idem=True)
    check("I-19-block-enforced", "FR-MSG-004 / I-19",
          "a blocked user can neither initiate nor continue contact with the blocker", r,
          r.status_code in (403, 409), f"{r.status_code} {r.text[:160]}")
    r = seller.get("/me/blocks")
    check("MSG-004-list-blocks", "FR-MSG-004", "blocks are listable", r, r.status_code == 200,
          f"{len(items(r))} blocks")
    r = seller.delete(f"/me/blocks/{buyer.user_id}")
    check("MSG-004-unblock", "FR-MSG-004", "a block can be removed", r,
          r.status_code in (200, 204), r.text[:160])

# ---------- FR-MSG-005 report -> moderation queue ----------
if LID:
    r = third.post("/reports", json={
        "subjectType": "LISTING", "subjectId": LID,
        "reason": "Spam deb hisoblayman"}, idem=True)
    check("MSG-005-report", "FR-MSG-005 / FR-MOD-001",
          "a report is created and enters the moderation queue", r,
          r.status_code in (200, 201, 202), r.text[:250])

ah.dump("/home/ameer/.claude/jobs/06393b27/tmp/res_messaging.json")
