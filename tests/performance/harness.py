"""The async HTTP load driver: starts a REAL `uvicorn` process serving `main:app` (not FastAPI's
`TestClient` -- `TestClient` runs its own blocking anyio portal under the hood and would itself
distort concurrency measurements, confirmed the hard way while building `tests/e2e/
test_critical_buyer_seller_journey.py` earlier this session, see that file's own `client` fixture
docstring), drives bounded-concurrency waves of real HTTP requests via `httpx.AsyncClient`, and
reports p50/p95/p99 per named operation.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import subprocess
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

import httpx

_HEALTH_POLL_INTERVAL_SECONDS = 0.5
_HEALTH_POLL_TIMEOUT_SECONDS = 30.0


@dataclass
class OperationResult:
    name: str
    latencies_ms: list[float] = field(default_factory=list)
    errors: int = 0

    def percentile(self, p: float) -> float:
        if not self.latencies_ms:
            return float("nan")
        ordered = sorted(self.latencies_ms)
        index = min(len(ordered) - 1, int(len(ordered) * p / 100))
        return ordered[index]

    def to_dict(self) -> dict[str, float | int | str]:
        return {
            "name": self.name,
            "count": len(self.latencies_ms),
            "errors": self.errors,
            "p50_ms": round(self.percentile(50), 2),
            "p95_ms": round(self.percentile(95), 2),
            "p99_ms": round(self.percentile(99), 2),
        }


class UvicornServer:
    """Starts/stops a real `uvicorn main:app` subprocess. Not a context manager over the event
    loop's own lifecycle -- the server runs in a genuinely separate OS process, exactly as it
    does in production, so the benchmark measures real inter-process HTTP overhead too."""

    def __init__(self, *, host: str = "127.0.0.1", port: int = 8321) -> None:
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self._process: subprocess.Popen[bytes] | None = None

    async def start(self) -> None:
        # A one-off startup call, not a hot loop -- `Path`'s sync I/O and `Popen`'s blocking
        # spawn are both deliberate here: spawning a REAL, separate uvicorn OS process (matching
        # production) is this class's entire purpose, not something to route through an async
        # subprocess API for a single, non-repeated call.
        repo_root = Path(__file__).resolve().parents[2]  # noqa: ASYNC240
        env = dict(os.environ)
        env["PYTHONPATH"] = f"apps/backend/src:packages/shared/src:.:{env.get('PYTHONPATH', '')}"
        self._process = subprocess.Popen(  # noqa: ASYNC220
            [
                sys.executable,
                "-m",
                "uvicorn",
                "main:app",
                "--host",
                self.host,
                "--port",
                str(self.port),
                "--log-level",
                "warning",
            ],
            cwd=str(repo_root / "apps" / "backend" / "src"),
            env=env,
        )
        await self._wait_healthy()

    async def _wait_healthy(self) -> None:
        deadline = time.monotonic() + _HEALTH_POLL_TIMEOUT_SECONDS
        async with httpx.AsyncClient() as client:
            while time.monotonic() < deadline:
                if self._process is not None and self._process.poll() is not None:
                    raise RuntimeError(f"uvicorn exited early with code {self._process.returncode}")
                try:
                    resp = await client.get(f"{self.base_url}/health", timeout=2.0)
                    if resp.status_code == 200:
                        return
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(_HEALTH_POLL_INTERVAL_SECONDS)
        raise TimeoutError(f"uvicorn did not become healthy within {_HEALTH_POLL_TIMEOUT_SECONDS}s")

    def stop(self) -> None:
        if self._process is not None:
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=10)
            self._process = None


async def run_operation_wave(
    *,
    name: str,
    call: Callable[[httpx.AsyncClient], Awaitable[None]],
    client: httpx.AsyncClient,
    total_requests: int,
    concurrency: int,
    warmup_requests: int = 5,
) -> OperationResult:
    """Discards `warmup_requests` (cold-cache/cold-connection-pool effects), then drives
    `total_requests` at bounded `concurrency`, recording per-request wall-clock latency."""
    for _ in range(warmup_requests):
        with contextlib.suppress(httpx.HTTPError):
            await call(client)

    result = OperationResult(name=name)
    semaphore = asyncio.Semaphore(concurrency)

    async def _one() -> None:
        started = time.monotonic()
        try:
            await call(client)
        except httpx.HTTPError:
            result.errors += 1
            return
        result.latencies_ms.append((time.monotonic() - started) * 1000)

    async def _bounded() -> None:
        async with semaphore:
            await _one()

    await asyncio.gather(*(_bounded() for _ in range(total_requests)))
    return result


def write_report(
    results: list[OperationResult], path: Path, *, metadata: dict[str, object]
) -> None:
    payload = {
        "metadata": metadata,
        "operations": [r.to_dict() for r in results],
    }
    path.write_text(json.dumps(payload, indent=2, default=str))
