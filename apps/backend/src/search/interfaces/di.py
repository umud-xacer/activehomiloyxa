"""Composition-root OVERRIDE POINT for search's router dependency (mirrors `catalog.interfaces.
di`'s own docstring exactly: DIP -- `search.interfaces` never imports `search.infrastructure`,
`no-infra-inbound-search` tools/importlinter.cfg). This function exists only so `search/interfaces/
routers.py` has a stable, importable `Depends(...)` target; the real implementation is registered
by the app factory via `app.dependency_overrides[...]` (`apps/backend/src/composition_root.py`,
imported only from `apps/backend/src/main.py`).

No `ActingUser` dependency here: every search-tagged OpenAPI operation declares `security: []`
(public, `contracts/openapi.yaml`) -- search never needs to know who is asking."""

from __future__ import annotations

from search.application import SearchUseCases


async def get_search_use_cases() -> SearchUseCases:
    raise NotImplementedError(
        "get_search_use_cases was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )
