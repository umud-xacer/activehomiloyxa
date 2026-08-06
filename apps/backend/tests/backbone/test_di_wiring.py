"""Proves the composition-root DI pattern (backbone.di.example) works end-to-end over real HTTP
request handling -- mounted on a throwaway app here only, never on the real one (see
backbone/di/example.py's module docstring for why)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backbone.di.example import (
    FakeHealthCheckAdapter,
    HealthCheckPort,
    HealthCheckUseCase,
    example_router,
)


def test_wiring_proof_endpoint_resolves_the_full_chain() -> None:
    app = FastAPI()
    app.include_router(example_router)
    client = TestClient(app)

    response = client.get("/__wiring_proof/health-check")

    assert response.status_code == 200
    assert response.json() == {"healthy": True}


async def test_the_use_case_never_constructs_a_concrete_adapter_itself() -> None:
    """The use case only ever sees the Protocol -- swap in a different port implementation and
    it must still work, since it depends on the abstraction, not FakeHealthCheckAdapter."""

    class AlwaysUnhealthyAdapter:
        async def check(self) -> bool:
            return False

    port: HealthCheckPort = AlwaysUnhealthyAdapter()
    use_case = HealthCheckUseCase(port)

    assert await use_case.execute() is False


async def test_fake_adapter_satisfies_the_port_protocol_structurally() -> None:
    adapter = FakeHealthCheckAdapter()
    assert hasattr(adapter, "check")
    assert await adapter.check() is True
