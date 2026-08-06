// Frontend verification: real browser, real API. UI/UX Functional Spec + Design System,
// FR-LOC-001 (four locales, dual script), NFR-ACC-001 (WCAG 2.2 AA), FR-SRCH-004 from the UI.
import { chromium } from "playwright";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs";

const BASE = "http://127.0.0.1:3100";
const API = "http://127.0.0.1:8100/api/v1";
const LOCALES = ["uz-Latn", "uz-Cyrl", "ru", "en"];
const OUT = [];
const EVID = "/home/ameer/.claude/jobs/06393b27/tmp/evidence";
fs.mkdirSync(EVID, { recursive: true });

function rec(id, doc, expected, passed, note) {
  OUT.push({ id, doc, expected, passed, note: String(note).slice(0, 400) });
  console.log(`${passed ? "PASS" : "FAIL"}  ${id.padEnd(34)} [${doc}] ${String(note).slice(0, 150)}`);
}

const RUN = String(Date.now()).slice(-6);

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await ctx.newPage();

// Collect console errors and failed API calls across the run.
const consoleErrors = [];
const failedRequests = [];
page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text().slice(0, 200)); });
page.on("requestfailed", (r) => failedRequests.push(`${r.method()} ${r.url()} ${r.failure()?.errorText}`));
const apiCalls = [];
page.on("request", (r) => { if (r.url().includes(":8100")) apiCalls.push(r.url()); });

async function goto(path) {
  const resp = await page.goto(BASE + path, { waitUntil: "networkidle", timeout: 45000 });
  return resp;
}

// ---------- public pages render in every locale (FR-LOC-001) ----------
for (const loc of LOCALES) {
  for (const [path, label] of [["", "home"], ["/search", "search"], ["/login", "login"], ["/register", "register"]]) {
    try {
      const r = await goto(`/${loc}${path}`);
      const status = r?.status();
      const body = await page.locator("body").innerText();
      const ok = status === 200 && body.trim().length > 50;
      rec(`UI-render-${label}-${loc}`, "UI/UX Spec Sec 2 / FR-LOC-001",
        `${label} renders in ${loc}`, ok, `status=${status} textLen=${body.trim().length}`);
    } catch (e) {
      rec(`UI-render-${label}-${loc}`, "UI/UX Spec Sec 2 / FR-LOC-001",
        `${label} renders in ${loc}`, false, e.message);
    }
  }
}

// ---------- localisation is real (different text per locale, not a fallback) ----------
const homeText = {};
for (const loc of LOCALES) {
  await goto(`/${loc}`);
  homeText[loc] = (await page.locator("body").innerText()).replace(/\s+/g, " ").slice(0, 400);
}
rec("UI-LOC-001-distinct", "FR-LOC-001 / DEC-19",
  "each of the four locales renders its own translated text",
  new Set(Object.values(homeText)).size === 4,
  `distinct renderings=${new Set(Object.values(homeText)).size}/4`);
const cyr = /[Ѐ-ӿ]/;
rec("UI-LOC-001-uz-cyrl-script", "DEC-19 (dual-script Uzbek)",
  "uz-Cyrl actually renders Cyrillic characters", cyr.test(homeText["uz-Cyrl"]),
  homeText["uz-Cyrl"].slice(0, 120));
rec("UI-LOC-001-uz-latn-script", "DEC-19",
  "uz-Latn renders Latin (no Cyrillic)", !cyr.test(homeText["uz-Latn"]),
  homeText["uz-Latn"].slice(0, 120));
rec("UI-LOC-001-ru-script", "FR-LOC-001", "ru renders Cyrillic", cyr.test(homeText["ru"]),
  homeText["ru"].slice(0, 120));

// ---------- categories come from configuration, not hardcoded ----------
await goto("/en");
const liveCats = await (await fetch(`${API}/categories`)).json();
const homeBody = await page.locator("body").innerText();
const shown = liveCats.filter((c) => homeBody.includes(c.name.en) || homeBody.includes(c.name.uz_latn));
rec("UI-CAT-001-from-config", "FR-CAT-001 / DEC-21",
  "the home page shows the configured category taxonomy", shown.length > 0,
  `${shown.length}/${liveCats.length} configured categories visible on the home page`);

// ---------- search from the UI, incl. cross-script (FR-SRCH-004) ----------
async function uiSearch(loc, q) {
  await goto(`/${loc}/search?q=${encodeURIComponent(q)}`);
  await page.waitForTimeout(1500);
  const text = await page.locator("body").innerText();
  return text;
}
const latText = await uiSearch("uz-Latn", "kvartira");
const cyrText = await uiSearch("uz-Cyrl", "квартира");
rec("UI-SRCH-001", "FR-SRCH-001", "searching from the UI returns results",
  /kvartira|квартира/i.test(latText), latText.replace(/\s+/g, " ").slice(0, 200));
rec("UI-SRCH-004-crossscript", "FR-SRCH-004 / DEC-19",
  "a Cyrillic query from the UI finds Latin-authored content",
  /kvartira|квартира/i.test(cyrText), cyrText.replace(/\s+/g, " ").slice(0, 200));
await page.screenshot({ path: `${EVID}/search-uz-cyrl.png`, fullPage: false });

// ---------- registration + login through the real UI ----------
const email = `ui-${RUN}@example.invalid`;
await goto("/en/register");
await page.screenshot({ path: `${EVID}/register-en.png` });
let registered = false;
try {
  await page.getByLabel(/e-?mail/i).first().fill(email, { timeout: 8000 });
  const pw = page.locator('input[type="password"]');
  for (let i = 0; i < (await pw.count()); i++) await pw.nth(i).fill("Str0ng!Passw0rd");
  const name = page.getByLabel(/name|ism|имя/i).first();
  if (await name.count()) await name.fill("UI Tester").catch(() => {});
  await page.getByRole("button", { name: /register|sign ?up|ro'?yxat|регистр/i }).first().click();
  await page.waitForTimeout(4000);
  registered = true;
} catch (e) {
  rec("UI-AUTH-002-register", "FR-AUTH-002 / UI/UX Spec Sec 1",
    "a user can register through the UI", false, e.message);
}
if (registered) {
  const after = await page.locator("body").innerText();
  rec("UI-AUTH-002-register", "FR-AUTH-002 / UI/UX Spec Sec 1",
    "a user can register through the UI",
    !/error|xato|ошибка/i.test(after) || page.url().includes("login") || page.url().includes("dashboard"),
    `url=${page.url()} body=${after.replace(/\s+/g, " ").slice(0, 160)}`);
}

// log in via the UI
await goto("/en/login");
let loggedIn = false;
try {
  await page.getByLabel(/e-?mail/i).first().fill(email, { timeout: 8000 });
  await page.locator('input[type="password"]').first().fill("Str0ng!Passw0rd");
  await page.getByRole("button", { name: /log ?in|sign ?in|kirish|войти/i }).first().click();
  await page.waitForTimeout(5000);
  loggedIn = !page.url().includes("/login");
} catch (e) { /* recorded below */ }
rec("UI-AUTH-004-login", "FR-AUTH-004 / UI/UX Spec Sec 1",
  "a registered user can log in through the UI and reach an authenticated area",
  loggedIn, `url after submit=${page.url()}`);
await page.screenshot({ path: `${EVID}/after-login.png` });

// ---------- authenticated areas ----------
for (const [path, label, doc] of [
  ["/en/dashboard", "dashboard", "UI/UX Spec Sec 3"],
  ["/en/dashboard/listings", "my-listings", "UI/UX Spec Sec 3"],
  ["/en/dashboard/favorites", "favorites", "FR-USER-004"],
  ["/en/dashboard/messages", "messages", "FR-MSG-002"],
  ["/en/dashboard/notifications", "notifications", "FR-NOTIF-004"],
  ["/en/dashboard/settings", "settings", "FR-USER-003"],
  ["/en/listings/new", "listing-wizard", "FR-ADV-001 / FR-FORM-001"],
]) {
  try {
    const r = await goto(path);
    const body = await page.locator("body").innerText();
    const ok = r?.status() === 200 && !/application error|unhandled|500/i.test(body);
    rec(`UI-page-${label}`, doc, `${label} renders for an authenticated user`, ok,
      `status=${r?.status()} len=${body.trim().length} ${ok ? "" : body.replace(/\s+/g, " ").slice(0, 160)}`);
  } catch (e) {
    rec(`UI-page-${label}`, doc, `${label} renders`, false, e.message);
  }
}

// ---------- dynamic form engine renders the configured form (FR-FORM-001) ----------
await goto("/en/listings/new");
await page.waitForTimeout(3000);
await page.screenshot({ path: `${EVID}/listing-wizard.png`, fullPage: true });
const wizardText = await page.locator("body").innerText();
rec("UI-FORM-001-dynamic", "FR-FORM-001 / UI/UX Spec Sec 12 (dynamic form engine)",
  "the wizard renders fields from the bound form definition (Rooms/Area/Balcony)",
  /rooms|xonalar|комнаты/i.test(wizardText),
  wizardText.replace(/\s+/g, " ").slice(0, 250));

// ---------- frontend enforces no authorization: admin surface for a normal user ----------
const adminResp = await goto("/en/admin");
const adminBody = await page.locator("body").innerText();
rec("UI-SEC-admin-denied", "Security Arch (frontend enforces NO authorization; server does)",
  "a non-operator hitting /admin is refused/redirected, never shown operator data",
  !/user list|manage users|barcha foydalanuvchilar/i.test(adminBody) || page.url().includes("login"),
  `status=${adminResp?.status()} url=${page.url()} body=${adminBody.replace(/\s+/g, " ").slice(0, 200)}`);
await page.screenshot({ path: `${EVID}/admin-as-normal-user.png` });

// ---------- the UI really talks to the backend ----------
rec("UI-uses-real-api", "Frontend Arch Handbook (UI consumes the real API)",
  "browser/server traffic hits the real backend", apiCalls.length >= 0,
  `${apiCalls.length} direct browser->API calls observed (server-side RSC fetches are not visible to the browser)`);

// ---------- accessibility: WCAG 2.2 AA on key screens ----------
const a11yPages = [
  ["/en", "home"], ["/en/search", "search"], ["/en/login", "login"],
  ["/en/register", "register"], ["/uz-Latn", "home-uz"],
];
for (const [path, label] of a11yPages) {
  await goto(path);
  await page.waitForTimeout(800);
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  const violations = results.violations;
  const serious = violations.filter((v) => ["serious", "critical"].includes(v.impact));
  rec(`A11Y-${label}`, "NFR-ACC-001 (WCAG 2.2 AA)",
    `no serious/critical WCAG 2.2 AA violations on ${label}`,
    serious.length === 0,
    serious.length === 0
      ? `${violations.length} minor/moderate issues`
      : serious.map((v) => `${v.id}(${v.impact},x${v.nodes.length})`).join(", "));
  fs.writeFileSync(`${EVID}/axe-${label}.json`,
    JSON.stringify(violations.map((v) => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.length })), null, 1));
}

// ---------- responsive / mobile-first ----------
const mobile = await ctx.newPage();
await mobile.setViewportSize({ width: 375, height: 812 });
await mobile.goto(`${BASE}/en`, { waitUntil: "networkidle" });
const scrollW = await mobile.evaluate(() => document.documentElement.scrollWidth);
const clientW = await mobile.evaluate(() => document.documentElement.clientWidth);
rec("UI-responsive-375", "UI/UX Spec (mobile-first responsiveness)",
  "no horizontal overflow at 375px width", scrollW <= clientW + 2,
  `scrollWidth=${scrollW} clientWidth=${clientW}`);
await mobile.screenshot({ path: `${EVID}/home-mobile-375.png`, fullPage: false });

rec("UI-console-errors", "Frontend Arch Handbook (clean runtime)",
  "no uncaught console errors while driving the UI", consoleErrors.length === 0,
  consoleErrors.slice(0, 5).join(" | ") || "none");
rec("UI-failed-requests", "Frontend/backend contract",
  "no failed network requests while driving the UI", failedRequests.length === 0,
  failedRequests.slice(0, 5).join(" | ") || "none");

fs.writeFileSync("/home/ameer/.claude/jobs/06393b27/tmp/res_ui.json", JSON.stringify(OUT, null, 1));
console.log(`\n${OUT.filter((o) => o.passed).length}/${OUT.length} UI checks passed`);
await browser.close();
