"""WIRING PROOF ONLY -- not a real feature, not part of the API contract. Demonstrates the
composition-root dependency-injection pattern every module's real use cases follow (Playbook
Sec 6: "use cases receive their ports, never construct concrete adapters ... the composition
root wires adapters to ports"): a port (`HealthCheckPort`), a fake infrastructure-style adapter
(`FakeHealthCheckAdapter`), an application-style use case that only knows the port
(`HealthCheckUseCase`), and FastAPI `Depends` providers that wire them together at the edge.

`example_router` exists so a test can mount it on a throwaway `FastAPI()` instance and drive it
with `TestClient` to prove the chain works end-to-end over real HTTP request handling -- it must
never be mounted on the real app (`apps/backend/src/main.py`): its path is not an operationId in
contracts/openapi.yaml, and CLAUDE.md forbids exactly that ("never hand-write or guess ... an
endpoint that isn't an operationId in this spec").
"""

from __future__ import annotations

from typing import Protocol

from fastapi import APIRouter, Depends


class HealthCheckPort(Protocol):
    """The port: what the use case needs, not how it's provided."""

    async def check(self) -> bool: ...


class FakeHealthCheckAdapter:
    """infrastructure/-style adapter -- trivially fake on purpose (a real one would ping a
    dependency); the point being proven is the wiring, not this check's usefulness."""

    async def check(self) -> bool:
        return True


class HealthCheckUseCase:
    """application/-style use case -- receives its port through the constructor, never
    constructs `FakeHealthCheckAdapter` (or any concrete adapter) itself."""

    def __init__(self, port: HealthCheckPort) -> None:
        self._port = port

    async def execute(self) -> bool:
        return await self._port.check()


def get_health_check_port() -> HealthCheckPort:
    """The composition root: the one place that knows which concrete adapter satisfies the
    port. A real module swaps this for its real adapter; callers above this line never do."""
    return FakeHealthCheckAdapter()


def get_health_check_use_case(
    port: HealthCheckPort = Depends(get_health_check_port),
) -> HealthCheckUseCase:
    return HealthCheckUseCase(port)


example_router = APIRouter()


@example_router.get("/__wiring_proof/health-check")
async def wiring_proof_endpoint(
    use_case: HealthCheckUseCase = Depends(get_health_check_use_case),
) -> dict[str, bool]:
    return {"healthy": await use_case.execute()}
