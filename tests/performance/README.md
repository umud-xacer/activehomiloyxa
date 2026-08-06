# tests/performance/ — P-21 benchmark harness

Repeatable benchmark harness for NFR-PERF-001 (search p95 < 500ms), NFR-PERF-002 (interactive
API p95 < 300ms), and the measured (not hard-SLO'd) async-lag windows SAD §19 names as an
accepted trade-off. Drives a REAL `uvicorn main:app` subprocess through real HTTP requests
(`httpx.AsyncClient`) — never FastAPI's `TestClient`, which runs its own blocking anyio portal
and would itself distort concurrency measurements (confirmed the hard way while building
`tests/e2e/test_critical_buyer_seller_journey.py` earlier in this project).

## Running it

Needs the real dev stack (`docker start active-home-postgres-1 active-home-redis-1
active-home-opensearch-1 active-home-minio-1` if any container is stopped) and the usual env
vars every cross-cutting suite in this repo needs:

```bash
export PYTHONPATH="apps/backend/src:packages/shared/src:."
export POSTGRES_HOST=localhost POSTGRES_PORT=5432 POSTGRES_DB=active_home POSTGRES_USER=active_home POSTGRES_PASSWORD=active_home_local_dev_only
export REDIS_HOST=localhost REDIS_PORT=6379
export OPENSEARCH_HOST=localhost OPENSEARCH_PORT=9200
```

1. **Seed** (idempotent — tops up rather than duplicating on re-run):
   ```bash
   python -m tests.performance.seed_cli --scale=phase1   # NFR-SCALE-001 figures: 10k users / 100k listings / 20k favorites / 2k conversations
   python -m tests.performance.seed_cli --scale=smoke    # 200 users / 1k listings / 200 favorites / 50 conversations -- for quickly validating the harness itself
   ```
   Seeds through the REAL use cases (`ListingUseCases`, `AccountUseCases`, etc. — the exact
   same classes `composition_root.py` wires into the real app), never a raw bulk `INSERT`, so
   the seeded data has the same invariants production data would have. Writes into the SAME
   OpenSearch index (`listing_search`) the real app reads from — this MUST match
   `composition_root._SEARCH_INDEX_NAME` exactly, or every search request 404s against
   OpenSearch and silently degrades to the Postgres fallback path (a confirmed defect in an
   earlier pass of this harness — see "Known gaps" below).

2. **Run a benchmark**:
   ```bash
   pytest -c tools/pytest.ini --rootdir=. tests/performance/test_benchmark_search.py -s
   pytest -c tools/pytest.ini --rootdir=. tests/performance/test_benchmark_interactive.py -s
   pytest -c tools/pytest.ini --rootdir=. tests/performance/test_benchmark_write_path.py -s
   pytest -c tools/pytest.ini --rootdir=. tests/performance/test_benchmark_async_lag.py -s
   ```
   Each writes a `baseline_report_*.json` (p50/p95/p99 per operation) into this directory.
   `-s` shows each operation's numbers as they complete.

3. **Tune concurrency/volume** via env vars (defaults are conservative for a shared/small host):
   `PERF_REQUESTS_PER_OPERATION` (default 100), `PERF_CONCURRENCY` (default 20).

4. **Clean up `listing_search` afterward** if you need `tests/e2e/`/other suites that also hit
   the real search index to pass cleanly right after a benchmark run — the seed script writes
   into the SAME real index the whole app uses, so leftover benchmark documents can bury a
   different test's own single expected hit past the first results page:
   ```bash
   curl -s -X DELETE "http://localhost:9200/listing_search"
   ```
   (`ensure_index()` recreates it empty on the next real request/re-seed.)

## What each file does

- `seed.py` / `seed_cli.py` — synthetic dataset generator (TEST-01/AIR-16: no real PII) and its
  CLI entrypoint. `SeedScale` has two presets: `PHASE1_SCALE` (the documented NFR-SCALE-001
  figures) and `SMOKE_SCALE` (a small scale for quickly validating the harness).
- `harness.py` — `UvicornServer` (starts/stops the real subprocess), `run_operation_wave`
  (bounded-concurrency request driver with warm-up discard), `write_report`.
- `operations.py` — the named HTTP operations under test, one function per SLO-relevant call.
- `test_benchmark_search.py` — NFR-PERF-001: full-text, faceted, geo/radius, cross-script
  (uz_latn↔uz_cyrl), suggest.
- `test_benchmark_interactive.py` — NFR-PERF-002: listing detail, authenticated `/me`,
  conversation history, banner serve, listing create+publish.
- `test_benchmark_write_path.py` — aggregate+outbox commit latency, isolated from HTTP overhead
  (measured at the use-case level).
- `test_benchmark_async_lag.py` — outbox→search indexing lag. No hard SLO (SAD §19 names this
  window as an accepted trade-off, "handled in UX," not a defect) — measured and reported, never
  asserted PASS/FAIL against an invented number. Uses its own isolated OpenSearch index (not
  `listing_search`) since it drives the handler in-process, not through the real running app.

## Known gaps / environmental limitations (disclosed, not hidden)

- **This sandbox is not the documented Phase-1 VM** (Infra doc: one 8-vCPU/32GB host). It is a
  disk-constrained, shared, multi-tenant host (other unrelated projects' Docker resources also
  live on the same volume) — absolute latency numbers measured here should be treated as
  directional, not a certification of the documented hardware's real-world performance. See the
  P-21 PERFORMANCE REPORT for the full disclosure.
- **Full Phase-1 scale (100k listings) has not been successfully seeded+benchmarked in this
  environment** — disk space (as low as ~1.4GB free on a 147GB volume) and shared-host
  contention made a stable large-scale run impractical. `SMOKE_SCALE` (1,000 listings) is the
  largest scale actually exercised end-to-end so far.
- **`test_benchmark_interactive.py`'s `listing_detail`/`conversation_history` operations
  currently error** (`ListingNotFoundError`/`NotAParticipantError`) — the `sample_listing_id`/
  `sample_conversation_id` fixtures pick an arbitrary seeded row that isn't guaranteed to be
  owned by / visible to the benchmark's own bearer-token user. `authenticated_me`,
  `banner_serve`, and `listing_create_and_publish` all work correctly. Fixing the sample-data
  selection to guarantee ownership/participancy is a good next step for whoever picks this back
  up.
- A prior pass of this harness discovered `create_listing(..., publish=True)` raises a
  duplicate-key `IntegrityError` on `listing_transition` against real Postgres (confirmed,
  reproducible at concurrency=1) — a genuine catalog correctness defect, not a performance
  issue, so deliberately NOT fixed as part of P-21 (out of this task's scope). `seed.py` works
  around it by calling create-draft then publish as two separate use-case calls. See the P-21
  PERFORMANCE REPORT for the full trace.
