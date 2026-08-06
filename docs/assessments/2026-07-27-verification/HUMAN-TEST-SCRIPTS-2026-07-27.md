# Active Home v1 — Human Test Scripts (2026-07-27)

Every item here needs real external credentials or real human interaction, so it could not be
completed by automated verification. Each script states what was **already** verified
automatically (so you do not repeat it), what remains, exact steps, and the pass criteria with
its document citation.

**Before you start** — bring the stack up. Note that steps 2 and 5 are workarounds for
DEF-001 and DEF-014; if those are fixed, use the supported path instead.

```bash
# 1. fresh database
psql -h localhost -U active_home -d postgres \
  -c "DROP DATABASE IF EXISTS active_home_manual WITH (FORCE);" \
  -c "CREATE DATABASE active_home_manual OWNER active_home;"

# 2. WORKAROUND for DEF-001 — create the 13 module schemas before migrating
for s in admin ads analytics billing catalog configuration identity media \
         messaging moderation notifications profiles search; do
  psql -h localhost -U active_home -d active_home_manual -c "CREATE SCHEMA IF NOT EXISTS \"$s\";"
done

# 3. migrate every module
for ini in apps/backend/src/*/infrastructure/migrations/alembic.ini; do
  (cd "$(dirname "$ini")" && alembic upgrade head)
done

# 4. seed the base configuration (roles + platform settings)
PYTHONPATH=apps/backend/src python -m configuration.infrastructure.seed

# 5. WORKAROUND for DEF-014 — grant the first administrator directly.
#    Register a user through the API first, then:
#    INSERT INTO identity.role_assignment
#      (id, account_id, role_definition_head_id, role_definition_version_id,
#       role_code, acting_profile_id, assigned_at, assigned_by)
#    SELECT gen_random_uuid(), '<USER_ID>', h.id, h.current_version_id,
#           'super-admin', NULL, now(), '<USER_ID>'
#    FROM configuration.role_definition h WHERE h.code = 'super-admin';

# 6. start API, realtime gateway and the nine workers, then confirm
curl -s localhost:8000/health && curl -s localhost:8000/ready
```

---

## HTS-01 — Real SMS OTP delivery (Eskiz)

**Requirements:** FR-AUTH-001, FR-NOTIF-003, BRULE-01.
**Already verified automatically:** the Eskiz adapter really issues an HTTPS request to
`https://notify.eskiz.uz/api/auth/login` and correctly fails closed when the credentials are
placeholders. The request is formed and dispatched. An invalid/expired code is rejected (`422`).
**Remaining:** that a real code is actually delivered by SMS and that it authenticates.
**Prerequisites:** a funded Eskiz account; an Uzbek mobile number you control.

1. Set real values in `deployment/env/.env.local` and restart the API:
   `ESKIZ_EMAIL`, `ESKIZ_PASSWORD`, `ESKIZ_SENDER_NICKNAME`.
2. Request a code for registration:
   ```bash
   curl -i -X POST http://localhost:8000/api/v1/auth/otp \
     -H 'Content-Type: application/json' \
     -d '{"phoneNumber":"+998XXXXXXXXX","purpose":"REGISTRATION"}'
   ```
   **Pass:** `200`/`202`, and an SMS arrives on the handset within ~60 s from the configured
   sender nickname.
   *(If this returns `500 DEPENDENCY_DEGRADED`, the credentials are still wrong — that is
   DEF-016's masking of a provider error.)*
3. Verify with the code you received:
   ```bash
   curl -i -X POST http://localhost:8000/api/v1/auth/otp/verify \
     -H 'Content-Type: application/json' \
     -d '{"phoneNumber":"+998XXXXXXXXX","code":"<CODE>","purpose":"REGISTRATION"}'
   ```
   **Pass (FR-AUTH-001 acceptance 1):** `200` with an account and a session; the response sets
   the `ah_session` cookie.
4. **Negative — wrong code.** Repeat step 2, then verify with a deliberately wrong 6-digit code.
   **Pass (acceptance 2):** rejected with a clear message, no session issued.
5. **Negative — expired code.** Request a code, wait past `otp.expiry_minutes` (platform
   settings; default 5), then verify with the real code.
   **Pass (acceptance 2):** rejected as expired.
6. **Rate limiting.** Request 10 codes for the same number in a minute.
   **Record** whether throttling occurs — the SRS does not specify a limit, so if nothing
   throttles, record it as UNSPECIFIED (a documentation gap), not a defect.
7. Log in with phone OTP on an existing account (`purpose: "LOGIN"`).
   **Pass (FR-AUTH-004):** a session is established.

---

## HTS-02 — Google federated sign-in

**Requirements:** FR-AUTH-003.
**Already verified automatically:** an invalid `idToken` is refused (`422`); the endpoint exists
and validates input.
**Remaining:** the success path, and the account-linking rule.
**Prerequisites:** a Google Cloud OAuth 2.0 Web client; two Google accounts, one of whose email
matches an existing Active Home account.

1. Set `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` in the backend env and
   `NEXT_PUBLIC_GOOGLE_CLIENT_ID` in `apps/frontend/.env.local`. Add
   `http://localhost:3000/api/auth/google/callback` as an authorised redirect URI. Restart both.
2. Open `http://localhost:3000/en/login`, choose Google sign-in, complete the Google consent
   screen with a **new** Google account.
   **Pass (acceptance 1):** you land authenticated in the app; `GET /api/v1/me` returns an
   account whose email is the Google address.
3. **Account linking.** Register a normal email/password account using the *same* address as your
   second Google account. Log out. Now sign in with Google using that second account.
   **Pass (acceptance 2):** you are signed into the **existing** account — not a duplicate.
   Confirm with:
   ```sql
   SELECT count(*) FROM identity.user_account WHERE email = '<that address>';   -- expect 1
   SELECT method_type FROM identity.authentication_method
    WHERE account_id = '<id>';                                -- expect both PASSWORD and GOOGLE
   ```
4. **Negative.** Cancel at the Google consent screen.
   **Pass:** returned to login with a clear message and no session.

---

## HTS-03 — Web-push notifications

**Requirements:** FR-NOTIF-002, FR-NOTIF-004.
**Already verified automatically:** nothing — this path was not exercised at all.
**Prerequisites:** a real VAPID key pair (`npx web-push generate-vapid-keys`); Chrome or Firefox;
the site served over `https` or `http://localhost` (both are secure contexts).

1. Put the pair in `WEB_PUSH_VAPID_PUBLIC_KEY` / `WEB_PUSH_VAPID_PRIVATE_KEY` and restart the API
   and the notifications worker.
2. Log in through the UI, open **Settings**, enable web-push, and accept the browser permission
   prompt.
   **Pass:** the browser records a push subscription (DevTools → Application → Service Workers),
   and the backend stores it.
3. Trigger a documented EventKey — the simplest is to have a second user send you a chat message
   (`MessageSent`), or publish one of your listings (`ListingPublished`).
   **Pass (FR-NOTIF-002):** an OS-level notification appears, with text localised to the
   locale you were browsing in.
4. **Preference suppression (FR-NOTIF-004).** In Settings, disable web-push. Trigger the same
   event again.
   **Pass:** **no** push arrives, while the in-app notification list still shows the entry.
5. **No duplicates on redelivery.** With push enabled, restart the notifications worker
   immediately after triggering an event, so the outbox redelivers.
   **Pass:** the user receives the notification **once**, not twice.
6. Repeat step 3 in each of the four locales (`uz-Latn`, `uz-Cyrl`, `ru`, `en`).
   **Pass (FR-LOC-001):** the notification body is in the matching language and script.

---

## HTS-04 — Production email delivery

**Requirements:** FR-NOTIF-001.
**Already verified automatically:** templated, localised email is produced and delivered to a
local Mailpit sink with correct subjects and recipients; 50 notification rows were persisted.
**Remaining:** delivery through a real SMTP server with STARTTLS + AUTH, and deliverability.
**Prerequisites:** production SMTP credentials; a mailbox you control at an external provider.

1. Set `SMTP_HOST`, `SMTP_PORT` (587), `SMTP_USER`, `SMTP_PASSWORD` — replacing the shipped
   `CHANGE_ME_IN_SECRETS_STORE` placeholders — and restart the API and notifications worker.
2. Register a new account using an external address.
   **Pass:** the confirmation email arrives in the real inbox, not in spam, with the correct
   sender identity.
   **Note:** the message will contain only `Confirmation token: <token>` and there is nowhere to
   redeem it — that is DEF-005, already recorded. Verify **delivery**, not activation.
3. Trigger a listing-published notification for that user.
   **Pass:** the email arrives, rendered from the published `notification-template` configuration.
4. **Localisation.** Set the account locale to each of the four in turn and re-trigger.
   **Pass:** subject and body are in the matching language and script, including correct
   Cyrillic rendering for `uz-Cyrl` and `ru` (check encoding — no mojibake).
5. **Preference suppression.** Disable email in Settings, trigger again.
   **Pass:** no email; the in-app notification still appears.

---

## HTS-05 — Yandex Maps display

**Requirements:** FR-MAP-002, BRULE-09.
**Already verified automatically:** listing locations are stored and returned by the API and in
search hits (FR-MAP-001).
**Remaining:** actual map rendering.
**Note:** verify **DEF-006 first** — radius filtering is currently broken server-side, so the map
will show correct pins but the radius control will not narrow anything.
**Prerequisites:** a real `YANDEX_MAPS_API_KEY`.

1. Set the key in the backend env (and the frontend env if the map is client-rendered), restart.
2. Publish two listings with known coordinates — one in Tashkent (41.311, 69.240), one in
   Samarkand (39.654, 66.959).
3. Open the search page and switch to map view.
   **Pass (FR-MAP-002):** the Yandex map renders and both listings appear **at their correct
   locations**.
4. Open a listing detail page.
   **Pass:** a map shows that listing's location.
5. Set a 5 km radius around Tashkent.
   **Expected per FR-MAP-003:** only the Tashkent listing.
   **Currently expected to FAIL** — the Samarkand listing will also appear (DEF-006). Record
   whether the UI at least *sends* the radius parameter, which tells you whether the fix is
   purely server-side.

---

## HTS-06 — Media safety pipeline (EXIF stripping, malware)

**Requirements:** FR-MEDIA-003 (BRULE-12), FR-MEDIA-004.
**Already verified automatically:** upload, type and size validation; ≤10 images; video/PDF
refusal.
**Remaining:** the two safety behaviours, both of which need real files.
**Prerequisites:** ClamAV running with a current virus database; `exiftool`.

**EXIF/GPS stripping (FR-MEDIA-003)**
1. Take a photo with a phone that records GPS, or inject coordinates:
   `exiftool -GPSLatitude=41.311 -GPSLongitude=69.240 -GPSLatitudeRef=N -GPSLongitudeRef=E test.jpg`
2. Confirm the metadata is present: `exiftool test.jpg | grep -i gps`.
3. Upload it through the listing wizard and wait for the media worker to finish processing.
4. Download the **stored/served** object (the CDN URL from `GET /media/{id}`), then:
   `exiftool downloaded.jpg | grep -i gps`
   **Pass:** no GPS tags — no output.
   **Fail:** any GPS tag survives; that is a privacy defect against QR-06 and BRULE-12.

**Malware scanning (FR-MEDIA-004)**
5. Create the EICAR test file (harmless by design, detected by every scanner):
   ```bash
   printf '%s' 'X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*' > eicar.png
   ```
6. Request an upload target and `PUT` the bytes, then wait for the scan.
   **Pass:** the asset ends in a quarantined/rejected state, is **not** served, and cannot be
   attached to a listing. Check:
   ```sql
   SELECT scan_status FROM media.media_asset ORDER BY created_at DESC LIMIT 1;
   ```
   **Fail:** status becomes clean, or the file is retrievable from the CDN URL.
7. Confirm the listing it was destined for cannot reference it (I-04 requires every attachment to
   be a Clean image asset).

---

## HTS-07 — Time-dependent expiry paths

**Requirements:** FR-ADV-007, FR-PROF-007, FR-SUBS-004 (and I-13's withdrawal clause).
**Already verified automatically:** nothing — all three need elapsed time.
**Recommended approach:** rather than waiting 30 days, shorten the terms via configuration, which
also re-verifies that these really are configuration and not constants.

**Listing expiry & renewal (FR-ADV-007)**
1. Publish a `platform-settings` version with `listing.default_expiry_days` set to a very small
   value (the settings schema types it as `int`; if the smallest usable value is 1 day, plan the
   test overnight or manipulate `catalog.listing.expires_at` directly as a last resort).
2. Publish a listing, wait for expiry, and let the expiry sweep run.
   **Pass (FR-ADV-007):** the listing is no longer publicly visible (`GET /listings/{id}`
   anonymous → `404`) and disappears from search, while the owner can still see it.
3. Renew it (`POST /listings/{id}/status {"action":"RENEW"}`).
   **Pass:** visibility is restored; a transition row is recorded.

**Badge expiry & re-verification (FR-PROF-007, I-13)**
4. Author a `VERIFICATION` product with a short `term_days`, purchase it, and complete the
   verification flow to a `VALID` badge.
5. After the term elapses, re-fetch the business profile.
   **Pass:** the badge is withdrawn — not shown on the profile and not shown in search results.
6. Request verification again.
   **Pass:** a **new** case is created (the old terminal case is untouched and still immutable).

**Entitlement expiry (FR-SUBS-004)**
7. Author a `SUBSCRIPTION` product with a short `term_days` and a `max_active_listings` quota,
   purchase and confirm it.
8. After expiry, check `GET /me/entitlements`.
   **Pass:** the entitlement is no longer active, and its benefit stops applying — a promoted
   listing loses its `promoted` label in search, and the quota reverts.

---

## HTS-08 — Banner campaign lifecycle (largest untested area)

**Requirements:** FR-BANNER-001…005, FR-ADMIN-004.
**Already verified automatically:** placement slots and the `BANNER_PLACEMENT` product can be
authored and published; `/admin/campaigns` responds; `/banners/serve` returns `204` with no
active campaign.
**Remaining:** essentially the whole module. This is not blocked by external credentials — it was
a time-boxing decision — so it can be automated later; the steps are given here so the gap can be
closed either way.

1. As a business user with an acting profile, order the `BANNER_PLACEMENT` product with
   `targetType: "SLOT_BOOKING"` and the placement slot as `targetId`; have an operator confirm
   payment.
   **Pass:** a `BANNER_SLOT_BOOKING` entitlement becomes active.
2. Upload a banner creative (`ownerContextType: "BANNER_CREATIVE"`).
3. As an operator, `POST /admin/campaigns` referencing the slot, the creative and the entitlement.
   **Pass (FR-BANNER-001):** the campaign is created; without the entitlement it must be refused.
4. `POST /admin/campaigns/{id}/schedule` with a start in the future and an end after it.
   **Pass (FR-BANNER-002):** `GET /banners/serve?slotKey=home-hero` returns `204` **before** the
   start, the banner **during** the window, and `204` **after** the end.
5. **Targeting (FR-BANNER-003).** Schedule with a category/geo/language target, then request
   `/banners/serve` with matching and non-matching `categoryId`, `geo` and `language`.
   **Pass:** served only in the targeted contexts.
6. **Metrics (FR-BANNER-005).** `POST /banners/{campaignId}/impressions` and
   `POST /banners/{campaignId}/clicks`, then:
   ```sql
   SELECT metric_key, count(*) FROM analytics.metric_event
    WHERE metric_key LIKE 'BANNER%' GROUP BY 1;
   ```
   **Pass:** `BANNER_IMPRESSION_RECORDED` and `BANNER_CLICK_RECORDED` rows exist.
   **Also assert (Domain Model §5 BC-12):** these are **metric events**, not counters — confirm
   there is no incrementing counter column on the campaign row itself.
7. Pause, resume and end the campaign.
   **Pass:** serving stops and restarts accordingly, and each action is auditable.

---

## HTS-09 — Reproduce the `next dev` hydration failure

**Not a requirement — a verification-integrity item.**
During this run the Next.js **dev** server produced a completely non-interactive page (no tabs,
no dropdowns, no keyboard navigation), while the **production build worked perfectly**. That was
judged an environment artefact and deliberately **not** reported as a product defect. It needs a
second opinion, because if it reproduces on other machines it destroys the developer inner loop.

1. On a clean checkout: `cd apps/frontend && npm ci && npm run dev`.
2. Open `http://localhost:3000/en/register` and click the **Email** tab.
   **Expected:** the panel switches and email/password/name fields appear.
   **If it does not switch**, check the browser console for
   `WebSocket connection to 'ws://…/_next/webpack-hmr…' failed: ERR_INVALID_HTTP_RESPONSE`.
3. Then `npm run build && npm start` and repeat step 2.
   **If dev fails and production succeeds on your machine too**, this is a real developer-
   experience defect (likely Turbopack HMR) and should be filed. If dev works for you, the
   finding was correctly attributed to the verification environment and can be closed.
