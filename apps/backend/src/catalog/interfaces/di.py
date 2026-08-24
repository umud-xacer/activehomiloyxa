"""Composition-root OVERRIDE POINTS for catalog's router dependencies (mirrors
`media.interfaces.di`'s own docstring exactly: DIP -- `catalog.interfaces` never imports
`catalog.infrastructure`, `no-infra-inbound-catalog` tools/importlinter.cfg). These functions
exist only so `catalog/interfaces/routers.py` has a stable, importable `Depends(...)` target; the
real implementation is registered by the app factory via `app.dependency_overrides[...]`
(`apps/backend/src/composition_root.py`, imported only from `apps/backend/src/main.py`).

`get_optional_acting_user` backs the three unauthenticated operations (`listListings`/
`getListing`/`listListingImages`, `security: []` in `contracts/openapi.yaml`) that still want to
know *if* a caller happens to be authenticated (`getListing`'s own "non-owners see only visible
listings") without *requiring* it -- returns `None` rather than raising when no valid session is
present, unlike `get_acting_user`."""

from __future__ import annotations

from catalog.application import FavoriteUseCases, ListingUseCases
from catalog.interfaces.auth import ActingOperator, ActingUser


async def get_listing_use_cases() -> ListingUseCases:
    raise NotImplementedError(
        "get_listing_use_cases was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


async def get_favorite_use_cases() -> FavoriteUseCases:
    raise NotImplementedError(
        "get_favorite_use_cases was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


async def get_acting_user() -> ActingUser:
    raise NotImplementedError(
        "get_acting_user was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


async def get_optional_acting_user() -> ActingUser | None:
    raise NotImplementedError(
        "get_optional_acting_user was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )


async def get_acting_operator() -> ActingOperator:
    raise NotImplementedError(
        "get_acting_operator was not overridden by the composition root "
        "(app.dependency_overrides) -- see apps/backend/src/composition_root.py"
    )
