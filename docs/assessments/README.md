# Assessments

Dated, point-in-time reports **about** the product — audits, verifications, coverage mappings and
gap analyses. Each folder is a snapshot of what was true at the commit it names, and is **never
edited after the fact**; a later pass supersedes an earlier one by adding a new folder, not by
rewriting history.

These are *not* the approved specification. The frozen source of truth lives one level up:
the `Active-Home-*.docx` baseline documents in `docs/`, `docs/frontend_docs/`, and the decisions
in `docs/adr/`. Where an assessment and a baseline document disagree, the baseline wins and the
disagreement is a defect the assessment should have recorded.

## Passes, newest first

| Date | Folder | Pass | Headline |
|---|---|---|---|
| 2026-07-28 | [`2026-07-28-frontend-gap/`](2026-07-28-frontend-gap/) | Frontend documentation-vs-implementation gap analysis (P-FEGAP) | 72 findings: 8 Critical, 22 High. Frontend ~72% complete against its three approved documents; 5 gaps are contract-level and need ADRs, not frontend work |
| 2026-07-28 | [`2026-07-28-incomplete/`](2026-07-28-incomplete/) | Unfinished-work inventory (P-INCOMPLETE) | 34 items: 3 BLOCKER, 18 MAJOR. Code is clean; the product can't be installed, deployed or recovered, and 2 CI gates are red on `main` |
| 2026-07-27 | [`2026-07-27-verification/`](2026-07-27-verification/) | Behavioural functional verification (P-VERIFY) | 245 doc-cited checks against the running system, 223 passed. 21 defects, 3 BLOCKER. Includes captured evidence |
| 2026-07-24 | [`2026-07-24-audit/`](2026-07-24-audit/) | Static audit + gap backlog | Architecture/traceability audit, gap backlog (G-*), invariant coverage |
| 2026-07-24 | [`2026-07-24-acceptance/`](2026-07-24-acceptance/) | Requirement→test mapping (P-20) | All 89 FR ids mapped to a covering test; 11 NFR gaps, all infra/load-testing |

## What is in each

**`2026-07-28-frontend-gap/`** — the frontend-only view, measured against the three
`docs/frontend_docs/` documents rather than the backend suite.
* `FRONTEND-GAP-ANALYSIS-2026-07-28.md` — 72 findings (full 14-field treatment for Critical/High,
  dense tables for Medium/Low), a per-section compliance matrix for all three frontend documents,
  and a dependency-ordered 5-phase plan (~126 engineer-days) preceded by a Phase 0 of ADR decisions.
* Its distinctive result: three of the specification's central promises — configuration-driven
  navigation/branding/static pages, permission-key UI gating, and CSRF — **cannot be built against
  the frozen contract**, which exposes no public config snapshot, no permission keys on `Account`,
  and no CSRF scheme. Those are ADR items, not frontend defects; the code correctly escalated them
  in comments instead of inventing endpoints.
* Static pass only: no dev server, browser or backend was run, so responsive behaviour, contrast,
  focus order and screen-reader output are explicitly **unassessed** rather than passed.

**`2026-07-28-incomplete/`** — the current pick-up-and-work list.
* `UNFINISHED-WORK-2026-07-28.md` — narrative report, per-module completeness ratings,
  reconciliation with the earlier passes, and a dependency-ordered completion plan.
* `UNFINISHED-BACKLOG-2026-07-28.md` — all 34 items with kind, location, doc citation, evidence,
  effort, target prompt and a "done when" criterion.
* `INCOMPLETENESS-SCAN-2026-07-28.md` — raw mechanical sweep with `file:line`, plus the verbatim
  output of every quality gate.

**`2026-07-27-verification/`** — what the running system actually did.
* `VERIFICATION-REPORT-2026-07-27.md` — full narrative.
* `DEFECT-REGISTER-2026-07-27.md` — 21 defects with deterministic reproduction steps.
* `FUNCTIONAL-COVERAGE-MATRIX-2026-07-27.md` — every documented functionality, tested or justified.
* `HUMAN-TEST-SCRIPTS-2026-07-27.md` — 9 manual scripts for what needs real external credentials
  (OTP, Google, web-push, production email, maps, media safety, expiry paths, banners).
* `evidence/` — axe results, screenshots, per-check JSON, and the harness used.

**`2026-07-24-audit/`** — `AUDIT-REPORT`, `GAP-BACKLOG` (G-* ids, referenced from module
`TRACEABILITY.md` files), `INVARIANT-COVERAGE`.

**`2026-07-24-acceptance/`** — `mapping.md` (FR/NFR → test) and `gap_report.md` (the honest
accounting; read this one first). Moved here from `tests/acceptance/`, which held no tests.

## Reading them together

The passes overlap and occasionally disagree; the newest reconciles the others rather than
replacing them. Two things worth carrying:

* **A covering test is not evidence an acceptance criterion is met.** The 2026-07-24 mapping found
  all 89 FRs had a covering test; the 2026-07-27 verification then exercised the running system
  and found several of those FRs failing their stated criteria anyway.
* **Each pass sees what its method can see.** The static audit and the requirement mapping both
  scoped infrastructure out; the behavioural verification only tested what was reachable at
  runtime. The infrastructure and operations gaps went unnoticed until the 2026-07-28 pass walked
  the Infrastructure document's own required list.

## Adding a pass

Create `docs/assessments/<YYYY-MM-DD>-<kind>/`, name the commit it assessed, and add a row above.
Do not edit an earlier folder to make it agree with yours — record the disagreement instead.

Note for tooling: `tools/security/gitleaks.toml` allowlists `docs/assessments/.*`, because captured
evidence legitimately contains opaque-looking literals from throwaway local stacks. Keep synthetic
data synthetic — never paste a real credential into an assessment.
