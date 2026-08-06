"""Redis-backed `SessionRepository` adapter (Security Sec 3.2: "Sessions are server-side,
Redis-backed"; no JWT, no refresh tokens anywhere in this module -- SDR-01). Each session is
stored as the same JSON blob under two keys (`by_id`, `by_token`) so both `revokeSession`
(id-based) and cookie/bearer resolution (token-based) are O(1) without a secondary index; a
`by_account` Redis SET indexes session ids for `listSessions` and bulk revocation, lazily pruned
of expired ids at read time rather than kept in lockstep via its own TTL (which could shrink
below an individual session's remaining lifetime and evict live entries early)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

from redis.asyncio import Redis

from identity.domain import Session
from shared_kernel import BusinessProfileId, UserId

_KEY_PREFIX = "identity:session"


def _by_id_key(session_id: UUID) -> str:
    return f"{_KEY_PREFIX}:by_id:{session_id}"


def _by_token_key(token_hash: str) -> str:
    return f"{_KEY_PREFIX}:by_token:{token_hash}"


def _by_account_key(account_id: UserId) -> str:
    return f"{_KEY_PREFIX}:by_account:{account_id.value}"


def _serialize(session: Session) -> str:
    return json.dumps(
        {
            "id": str(session.id),
            "accountId": str(session.account_id.value),
            "tokenHash": session.token_hash,
            "actingProfileId": (
                str(session.acting_profile_id.value) if session.acting_profile_id else None
            ),
            "ipAddress": session.ip_address,
            "userAgent": session.user_agent,
            "createdAt": session.created_at.isoformat(),
            "expiresAt": session.expires_at.isoformat(),
            "revokedAt": session.revoked_at.isoformat() if session.revoked_at else None,
        }
    )


def _deserialize(raw: str | bytes) -> Session:
    data = json.loads(raw)
    return Session(
        id=UUID(data["id"]),
        account_id=UserId(value=UUID(data["accountId"])),
        token_hash=data["tokenHash"],
        acting_profile_id=(
            BusinessProfileId(value=UUID(data["actingProfileId"]))
            if data["actingProfileId"]
            else None
        ),
        ip_address=data["ipAddress"],
        user_agent=data["userAgent"],
        created_at=datetime.fromisoformat(data["createdAt"]),
        expires_at=datetime.fromisoformat(data["expiresAt"]),
        revoked_at=datetime.fromisoformat(data["revokedAt"]) if data["revokedAt"] else None,
    )


def _ttl_seconds(session: Session) -> int:
    remaining = session.expires_at - datetime.now(UTC)
    return max(int(remaining.total_seconds()), 1)


class RedisSessionRepository:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get_by_id(self, session_id: UUID) -> Session | None:
        raw = await self._redis.get(_by_id_key(session_id))
        return _deserialize(raw) if raw is not None else None

    async def get_by_token_hash(self, token_hash: str) -> Session | None:
        raw = await self._redis.get(_by_token_key(token_hash))
        return _deserialize(raw) if raw is not None else None

    async def list_for_account(self, account_id: UserId) -> list[Session]:
        session_ids = await self._redis.smembers(_by_account_key(account_id))
        sessions: list[Session] = []
        for raw_id in session_ids:
            session_id_str = raw_id.decode() if isinstance(raw_id, bytes) else raw_id
            session = await self.get_by_id(UUID(session_id_str))
            if session is None:
                await self._redis.srem(_by_account_key(account_id), raw_id)
                continue
            sessions.append(session)
        return sessions

    async def save(self, session: Session) -> None:
        payload = _serialize(session)
        ttl = _ttl_seconds(session)
        await self._redis.set(_by_id_key(session.id), payload, ex=ttl)
        await self._redis.set(_by_token_key(session.token_hash), payload, ex=ttl)
        await self._redis.sadd(_by_account_key(session.account_id), str(session.id))

    async def delete(self, session_id: UUID) -> None:
        session = await self.get_by_id(session_id)
        if session is None:
            return
        await self._redis.delete(_by_id_key(session_id))
        await self._redis.delete(_by_token_key(session.token_hash))
        await self._redis.srem(_by_account_key(session.account_id), str(session_id))

    async def delete_all_for_account(self, account_id: UserId) -> None:
        for session in await self.list_for_account(account_id):
            await self.delete(session.id)
        await self._redis.delete(_by_account_key(account_id))
