"""Composition-root OVERRIDE POINTS for ads' router dependencies (mirrors `billing.interfaces.
di`'s own docstring exactly: DIP -- `ads.interfaces` never imports `ads.infrastructure`,
`no-infra-inbound-ads` tools/importlinter.cfg). These functions exist only so `ads/interfaces/
routers.py` has a stable, importable `Depends(...)` target; the real implementation is
registered by the app factory via `app.dependency_overrides[...]`
(`apps/backend/src/composition_root.py`, imported only from `apps/backend/src/main.py`)."""

from __future__ import annotations

from ads.application import BannerServingUseCases, CampaignUseCases
from ads.interfaces.auth import ActingOperator


async def get_campaign_use_cases() -> CampaignUseCases:
    raise NotImplementedError(
        "get_campaign_use_cases was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


async def get_serving_use_cases() -> BannerServingUseCases:
    raise NotImplementedError(
        "get_serving_use_cases was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


async def get_acting_operator() -> ActingOperator:
    raise NotImplementedError(
        "get_acting_operator was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )
