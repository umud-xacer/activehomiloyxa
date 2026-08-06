"""Standalone seed entrypoint: `python -m tests.performance.seed_cli --scale=phase1`.

Needs the real dev stack up (`docker start active-home-postgres-1 active-home-redis-1
active-home-opensearch-1 active-home-minio-1` if any container is stopped) and the same env vars
every other suite in this repo needs (`POSTGRES_HOST`/`REDIS_HOST`/`OPENSEARCH_HOST` at minimum --
`tests/performance/README.md` has the full list, matching `tests/e2e/conftest.py::_DEFAULT_ENV`).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from opensearchpy import OpenSearch
from redis.asyncio import Redis

from backbone.persistence import make_engine, make_session_factory, redis_url
from catalog.infrastructure.persistence.base import CatalogBase
from configuration.infrastructure.persistence.base import ConfigurationBase
from identity.infrastructure.persistence.base import IdentityBase
from messaging.infrastructure.persistence.base import MessagingBase
from search.infrastructure.opensearch_index import OpenSearchIndexAdapter
from tests.integration.conftest import ensure_clean_schema
from tests.performance.seed import PHASE1_SCALE, SMOKE_SCALE, SeedScale, seed_all

_INDEX_NAME = "listing_search"
"""Must match `composition_root._SEARCH_INDEX_NAME` EXACTLY -- the benchmark exercises the real,
running app (a real `uvicorn` process reading through `composition_root._search_index_adapter()`,
hardcoded to this literal name, not env-configurable), so seeding into any other index name means
every search request silently 404s against OpenSearch and falls back to the Postgres degradation
path (`SearchUseCases`'s own `DegradationPolicy`) -- a confirmed defect in an earlier pass of this
same harness that produced fallback-path timings while believing it measured real OpenSearch."""

_DEFAULT_ENV: dict[str, str] = {
    "SESSION_COOKIE_NAME": "ah_session",
    "SESSION_SIGNING_KEY": "perf-test-signing-key-not-a-real-secret",
    "ESKIZ_API_BASE_URL": "https://example.invalid/eskiz",
    "ESKIZ_EMAIL": "perf-test@example.invalid",
    "ESKIZ_PASSWORD": "unused-perf-test-value",
    "ESKIZ_SENDER_NICKNAME": "unused-perf-test-value",
    "SMTP_HOST": "example.invalid",
    "SMTP_PORT": "587",
    "SMTP_USER": "unused-perf-test-value",
    "SMTP_PASSWORD": "unused-perf-test-value",
    "WEB_PUSH_VAPID_PUBLIC_KEY": "unused-perf-test-value",
    "WEB_PUSH_VAPID_PRIVATE_KEY": "unused-perf-test-value",
    "GOOGLE_OAUTH_CLIENT_ID": "unused-perf-test-value",
    "GOOGLE_OAUTH_CLIENT_SECRET": "unused-perf-test-value",
    "YANDEX_MAPS_API_KEY": "unused-perf-test-value",
    "MINIO_ENDPOINT": "localhost:9000",
    "MINIO_ROOT_USER": "active_home",
    "MINIO_ROOT_PASSWORD": "active_home_local_dev_only",
    "MINIO_MEDIA_BUCKET": "active-home-media",
    "MINIO_USE_TLS": "false",
    "MEDIA_CDN_BASE_URL": "http://localhost:8080/media",
    "MEDIA_PRESIGN_EXPIRY_SECONDS": "900",
    "CLAMAV_HOST": "localhost",
    "CLAMAV_PORT": "3310",
}


def _apply_default_env() -> None:
    for key, value in _DEFAULT_ENV.items():
        os.environ.setdefault(key, value)


async def _run(scale: SeedScale) -> None:
    _apply_default_env()
    engine = make_engine()
    session_factory = make_session_factory(engine)
    for schema, base in (
        ("configuration", ConfigurationBase),
        ("catalog", CatalogBase),
        ("identity", IdentityBase),
        ("messaging", MessagingBase),
    ):
        await ensure_clean_schema(engine, schema, base)

    redis_client: Redis = Redis.from_url(redis_url())
    async for key in redis_client.scan_iter("configuration:snapshot:*"):
        await redis_client.delete(key)

    client = OpenSearch(
        hosts=[
            {
                "host": os.environ.get("OPENSEARCH_HOST", "localhost"),
                "port": int(os.environ.get("OPENSEARCH_PORT", "9200")),
            }
        ]
    )
    index = OpenSearchIndexAdapter(client, index_name=_INDEX_NAME)
    await index.ensure_index()

    print(f"Seeding at scale: {scale}", file=sys.stderr)
    timings = await seed_all(session_factory, redis_client, index, scale)
    print(f"Done. Phase timings (seconds): {timings}", file=sys.stderr)
    await redis_client.aclose()
    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scale",
        choices=["phase1", "smoke"],
        default="phase1",
        help="phase1 = SRS NFR-SCALE-001 figures (10k users/100k listings/...); "
        "smoke = a small scale for quickly validating the harness itself",
    )
    args = parser.parse_args()
    scale = PHASE1_SCALE if args.scale == "phase1" else SMOKE_SCALE
    asyncio.run(_run(scale))


if __name__ == "__main__":
    main()
