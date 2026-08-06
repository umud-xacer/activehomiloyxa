"""Integration tests: `RedisSessionRepository` round-trip against real Redis (Security Sec 3.2:
"Sessions are server-side, Redis-backed"). P-05 deliverable: "integration tests for session
persistence and round-trip"."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from redis.asyncio import Redis

from identity.domain import Session
from identity.infrastructure.session_store import RedisSessionRepository
from shared_kernel import UserId

NOW = datetime(2026, 7, 11, tzinfo=UTC)


def _new_session(**overrides: object) -> Session:
    defaults: dict[str, object] = {
        "session_id": uuid4(),
        "account_id": UserId(value=uuid4()),
        "token_hash": f"hash-{uuid4()}",
        "ip_address": "1.2.3.4",
        "user_agent": "pytest",
        "now": NOW,
        "expires_at": NOW + timedelta(hours=720),
    }
    defaults.update(overrides)
    return Session.issue(**defaults)  # type: ignore[arg-type]


async def test_save_and_get_by_id_round_trips(redis_client: Redis) -> None:
    repo = RedisSessionRepository(redis_client)
    session = _new_session()
    await repo.save(session)

    fetched = await repo.get_by_id(session.id)
    assert fetched is not None
    assert fetched.token_hash == session.token_hash
    assert fetched.account_id == session.account_id


async def test_save_and_get_by_token_hash_round_trips(redis_client: Redis) -> None:
    repo = RedisSessionRepository(redis_client)
    session = _new_session()
    await repo.save(session)

    fetched = await repo.get_by_token_hash(session.token_hash)
    assert fetched is not None
    assert fetched.id == session.id


async def test_get_by_id_unknown_session_returns_none(redis_client: Redis) -> None:
    repo = RedisSessionRepository(redis_client)
    assert await repo.get_by_id(uuid4()) is None


async def test_list_for_account_returns_only_that_accounts_sessions(redis_client: Redis) -> None:
    repo = RedisSessionRepository(redis_client)
    account_id = UserId(value=uuid4())
    mine = _new_session(account_id=account_id)
    theirs = _new_session()
    await repo.save(mine)
    await repo.save(theirs)

    sessions = await repo.list_for_account(account_id)
    assert [s.id for s in sessions] == [mine.id]


async def test_delete_removes_both_id_and_token_hash_keys(redis_client: Redis) -> None:
    repo = RedisSessionRepository(redis_client)
    session = _new_session()
    await repo.save(session)

    await repo.delete(session.id)

    assert await repo.get_by_id(session.id) is None
    assert await repo.get_by_token_hash(session.token_hash) is None


async def test_delete_all_for_account_removes_every_session(redis_client: Redis) -> None:
    repo = RedisSessionRepository(redis_client)
    account_id = UserId(value=uuid4())
    first = _new_session(account_id=account_id)
    second = _new_session(account_id=account_id)
    await repo.save(first)
    await repo.save(second)

    await repo.delete_all_for_account(account_id)

    assert await repo.list_for_account(account_id) == []
    assert await repo.get_by_id(first.id) is None
    assert await repo.get_by_id(second.id) is None


async def test_session_expires_from_redis_after_ttl(redis_client: Redis) -> None:
    """Server-side session lifetime is enforced by Redis's own TTL, not just the domain's
    `require_valid` check -- a session already past its `expires_at` at save time is not
    retrievable at all."""
    repo = RedisSessionRepository(redis_client)
    session = _new_session(now=NOW, expires_at=NOW + timedelta(seconds=1))
    await repo.save(session)

    import asyncio

    await asyncio.sleep(1.5)
    assert await repo.get_by_id(session.id) is None
