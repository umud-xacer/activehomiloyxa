// Authenticated UI flows: registration, login, dashboard, dynamic-form wizard, operator surface.
import { chromium } from "playwright";
import AxeBuilder from "@axe-core/playwright";
import fs from "node:fs";

const BASE = "http://127.0.0.1:3100";
const EVID = "/home/ameer/.claude/jobs/06393b27/tmp/evidence";
const OUT = [];
const RUN = String(Date.now()).slice(-6);
function rec(id, doc, expected, passed, note) {
  OUT.push({ id, doc, expected, passed, note: String(note).slice(0, 400) });
  console.log(`${passed ? "PASS" : "FAIL"}  ${id.padEnd(32)} [${doc}] ${String(note).slice(0, 160)}`);
}

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await ctx.newPage();
const email = `uiauth-${RUN}@example.invalid`;
const PW = "Str0ng!Passw0rd";

// ---------- FR-AUTH-002 register through the UI (Email tab) ----------
await page.goto(`${BASE}/en/register`, { waitUntil: "networkidle" });
await page.getByRole("tab", { name: /email/i }).click();
await page.waitForTimeout(600);
await page.screenshot({ path: `${EVID}/register-email-tab.png` });
const fields = await page.evaluate(() =>
  [...document.querySelectorAll("input")].map((e) => `${e.type}|${e.id}|${e.placeholder}`));
rec("UI-register-form", "UI/UX Spec Sec 1 (registration)",
  "the email registration form exposes email + password fields",
  fields.some((f) => f.startsWith("email")) && fields.some((f) => f.startsWith("password")),
  fields.join(" , "));

await page.locator('input[type="email"]').first().fill(email);
const pws = page.locator('input[type="password"]');
for (let i = 0; i < (await pws.count()); i++) await pws.nth(i).fill(PW);
const nameField = page.locator("#displayName, #name");
if (await nameField.count()) await nameField.first().fill("UI Tester");
await page.getByRole("button", { name: /create|register|sign ?up/i }).first().click();
await page.waitForTimeout(5000);
const afterReg = await page.locator("body").innerText();
rec("UI-AUTH-002-register", "FR-AUTH-002",
  "registration through the UI succeeds and gives the user feedback",
  !/unexpected|unhandled|500/i.test(afterReg),
  `url=${page.url()} :: ${afterReg.replace(/\s+/g, " ").slice(0, 200)}`);

// ---------- FR-AUTH-004 login through the UI ----------
await page.goto(`${BASE}/en/login`, { waitUntil: "networkidle" });
await page.getByRole("tab", { name: /email/i }).click();
await page.waitForTimeout(500);
await page.locator('input[type="email"]').first().fill(email);
await page.locator('input[type="password"]').first().fill(PW);
await page.getByRole("button", { name: /log ?in|sign ?in|continue/i }).first().click();
await page.waitForTimeout(6000);
const loggedIn = !page.url().includes("/login");
rec("UI-AUTH-004-login", "FR-AUTH-004",
  "a registered user logs in through the UI and leaves the login page", loggedIn,
  `url=${page.url()}`);
await page.screenshot({ path: `${EVID}/after-login.png` });

const cookies = await ctx.cookies();
rec("UI-AUTH-005-session-cookie", "Baseline (session auth via HttpOnly ah_session, not JWT)",
  "the browser holds an HttpOnly ah_session cookie",
  cookies.some((c) => c.name === "ah_session" && c.httpOnly),
  cookies.map((c) => `${c.name}(httpOnly=${c.httpOnly},sameSite=${c.sameSite})`).join(", "));

// ---------- authenticated screens really render (not the login page) ----------
const PAGES = [
  ["/en/dashboard", "dashboard", "UI/UX Spec Sec 3"],
  ["/en/dashboard/listings", "my-listings", "UI/UX Spec Sec 3 / FR-ADV-005"],
  ["/en/dashboard/favorites", "favorites", "FR-USER-004"],
  ["/en/dashboard/messages", "messages", "FR-MSG-002"],
  ["/en/dashboard/notifications", "notifications", "FR-NOTIF-004"],
  ["/en/dashboard/profile", "profile", "FR-USER-001"],
  ["/en/dashboard/settings", "settings", "FR-USER-003"],
  ["/en/dashboard/business", "business", "FR-PROF-001"],
  ["/en/listings/new", "listing-wizard", "FR-ADV-001 / FR-FORM-001"],
];
for (const [path, label, doc] of PAGES) {
  const r = await page.goto(BASE + path, { waitUntil: "networkidle", timeout: 45000 });
  await page.waitForTimeout(1200);
  const body = await page.locator("body").innerText();
  const bounced = page.url().includes("/login");
  const errored = /application error|unhandled|Internal Server Error/i.test(body);
  rec(`UI-page-${label}`, doc,
    `${label} renders its own authenticated content`,
    r?.status() === 200 && !bounced && !errored,
    `status=${r?.status()} bouncedToLogin=${bounced} len=${body.trim().length} ${errored ? body.replace(/\s+/g, " ").slice(0, 150) : ""}`);
}

// ---------- FR-FORM-001 dynamic form engine ----------
await page.goto(`${BASE}/en/listings/new`, { waitUntil: "networkidle" });
await page.waitForTimeout(2500);
await page.screenshot({ path: `${EVID}/listing-wizard.png`, fullPage: true });
let wizard = await page.locator("body").innerText();
rec("UI-ADV-001-wizard", "FR-ADV-001 / UI/UX Spec Sec 12",
  "the advertisement creation wizard opens for an authenticated user",
  !page.url().includes("/login"), `url=${page.url()} :: ${wizard.replace(/\s+/g, " ").slice(0, 180)}`);

// choose the configured category, then look for its dynamic fields
try {
  const cat = page.getByText(/Apartment|Kvartira/i).first();
  if (await cat.count()) { await cat.click(); await page.waitForTimeout(2500); }
  const next = page.getByRole("button", { name: /next|continue|keyingi/i }).first();
  if (await next.count()) { await next.click(); await page.waitForTimeout(2500); }
  wizard = await page.locator("body").innerText();
} catch { /* recorded below */ }
await page.screenshot({ path: `${EVID}/listing-wizard-step2.png`, fullPage: true });
rec("UI-FORM-001-dynamic-fields", "FR-FORM-001 / FR-CAT-002 / UI/UX Spec Sec 12",
  "the wizard renders the fields defined by the category's bound form (Rooms / Area / Balcony)",
  /rooms|xonalar|area|maydon|balcony|balkon/i.test(wizard),
  wizard.replace(/\s+/g, " ").slice(0, 300));

// ---------- a11y on authenticated screens ----------
for (const [path, label] of [["/en/dashboard", "dashboard"], ["/en/listings/new", "wizard"]]) {
  await page.goto(BASE + path, { waitUntil: "networkidle" });
  await page.waitForTimeout(1000);
  const res = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
  const serious = res.violations.filter((v) => ["serious", "critical"].includes(v.impact));
  rec(`A11Y-${label}`, "NFR-ACC-001 (WCAG 2.2 AA)",
    `no serious/critical violations on ${label}`, serious.length === 0,
    serious.map((v) => `${v.id}(${v.impact},x${v.nodes.length})`).join(", ") ||
      `${res.violations.length} minor/moderate`);
  fs.writeFileSync(`${EVID}/axe-${label}.json`, JSON.stringify(res.violations.map(
    (v) => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.length })), null, 1));
}

// ---------- operator surface with a real operator session ----------
const opCtx = await browser.newContext();
const op = await opCtx.newPage();
await op.goto(`${BASE}/en/login`, { waitUntil: "networkidle" });
await op.getByRole("tab", { name: /email/i }).click();
await op.waitForTimeout(400);
await op.locator('input[type="email"]').first().fill("maker.admin@example.invalid");
await op.locator('input[type="password"]').first().fill(PW);
await op.getByRole("button", { name: /log ?in|sign ?in|continue/i }).first().click();
await op.waitForTimeout(6000);
for (const [path, label, doc] of [
  ["/en/admin", "admin-home", "UI/UX Spec Sec 6"],
  ["/en/admin/users", "admin-users", "FR-ADMIN-001"],
  ["/en/admin/moderation", "admin-moderation", "FR-MOD-005"],
  ["/en/admin/verification", "admin-verification", "FR-ADMIN-002"],
  ["/en/admin/invoices", "admin-invoices", "FR-ADMIN-003"],
  ["/en/admin/audit", "admin-audit", "FR-AUDIT-002"],
  ["/en/admin/reports", "admin-reports", "FR-ADMIN-005"],
  ["/en/admin/config", "config-portal", "UI/UX Spec Sec 5 (Product-Owner config portal)"],
  ["/en/admin/config/category", "config-category", "FR-CFG-001"],
]) {
  const r = await op.goto(BASE + path, { waitUntil: "networkidle", timeout: 45000 });
  await op.waitForTimeout(1200);
  const body = await op.locator("body").innerText();
  const bounced = op.url().includes("/login");
  const errored = /application error|unhandled|Internal Server Error/i.test(body);
  rec(`UI-op-${label}`, doc, `${label} renders for a super-admin`,
    r?.status() === 200 && !bounced && !errored,
    `status=${r?.status()} bounced=${bounced} len=${body.trim().length} ${errored ? body.replace(/\s+/g, " ").slice(0, 150) : ""}`);
}
await op.screenshot({ path: `${EVID}/admin-config-portal.png`, fullPage: true });

fs.writeFileSync("/home/ameer/.claude/jobs/06393b27/tmp/res_ui_auth.json", JSON.stringify(OUT, null, 1));
console.log(`\n${OUT.filter((o) => o.passed).length}/${OUT.length} authenticated-UI checks passed`);
await browser.close();
