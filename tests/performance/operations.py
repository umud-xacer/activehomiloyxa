"""The named operations the P-21 benchmark harness drives, one function per SLO-relevant call
(traced in each docstring). Every function takes a real `httpx.AsyncClient` bound to a real
running `uvicorn` instance and returns nothing -- the harness times the call itself, not this
module. `raise_for_status()` inside each function turns an unexpected HTTP failure into a harness
error rather than a silently-recorded-but-wrong latency sample.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class Operation:
    name: str
    slo_group: str  # "search" (NFR-PERF-001) | "interactive" (NFR-PERF-002) | "write" | "async"
    target_p95_ms: float | None  # None where no per-operation hard target exists


async def search_full_text(client: httpx.AsyncClient, *, base_url: str) -> None:
    """NFR-PERF-001. `GET /search?q=...` -- free-text, cross-script query."""
    resp = await client.get(f"{base_url}/api/v1/search", params={"q": "studio apartment"})
    resp.raise_for_status()


async def search_faceted(client: httpx.AsyncClient, *, base_url: str, category_id: str) -> None:
    """NFR-PERF-001. Faceted query -- filters on the one facet-eligible field the seed publishes
    (`rooms`)."""
    resp = await client.get(
        f"{base_url}/api/v1/search",
        params={"categoryId": category_id, "filters[rooms]": "2"},
    )
    resp.raise_for_status()


async def search_geo(client: httpx.AsyncClient, *, base_url: str) -> None:
    """NFR-PERF-001. Geo/radius query over the seed's Tashkent-bounded synthetic coordinates."""
    resp = await client.get(
        f"{base_url}/api/v1/search",
        params={"lat": 41.30, "lng": 69.25, "radiusKm": 15},
    )
    resp.raise_for_status()


async def search_cross_script(client: httpx.AsyncClient, *, base_url: str) -> None:
    """NFR-PERF-001/NFR-LOC-001. The same Latin query re-issued in Cyrillic -- proves both scripts
    hit the same analyzer path; seeded content is Latin-only synthetic text, so this exercises the
    cross-script MATCH machinery even though it won't hit rows the Latin query also finds."""
    resp = await client.get(f"{base_url}/api/v1/search", params={"q": "студия"})
    resp.raise_for_status()


async def search_suggest(client: httpx.AsyncClient, *, base_url: str) -> None:
    """NFR-PERF-001. `GET /search/suggest`."""
    resp = await client.get(f"{base_url}/api/v1/search/suggest", params={"q": "cozy"})
    resp.raise_for_status()


async def interactive_listing_detail(
    client: httpx.AsyncClient, *, base_url: str, listing_id: str
) -> None:
    """NFR-PERF-002. `GET /listings/{id}` -- public, unauthenticated read."""
    resp = await client.get(f"{base_url}/api/v1/listings/{listing_id}")
    resp.raise_for_status()


async def interactive_authenticated_me(
    client: httpx.AsyncClient, *, base_url: str, bearer_token: str
) -> None:
    """NFR-PERF-002. `GET /me` -- authenticated read."""
    resp = await client.get(
        f"{base_url}/api/v1/me", headers={"Authorization": f"Bearer {bearer_token}"}
    )
    resp.raise_for_status()


async def interactive_conversation_history(
    client: httpx.AsyncClient, *, base_url: str, conversation_id: str, bearer_token: str
) -> None:
    """NFR-PERF-002. `GET /conversations/{id}/messages` -- authenticated, paged history."""
    resp = await client.get(
        f"{base_url}/api/v1/conversations/{conversation_id}/messages",
        headers={"Authorization": f"Bearer {bearer_token}"},
    )
    resp.raise_for_status()


async def interactive_listing_create(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    bearer_token: str,
    category_id: str,
    title: str,
) -> str:
    """NFR-PERF-002. `POST /listings` (draft, unpublished) -- returns the new listing id."""
    resp = await client.post(
        f"{base_url}/api/v1/listings",
        headers={"Authorization": f"Bearer {bearer_token}"},
        json={
            "listingType": "ADVERTISEMENT",
            "categoryId": category_id,
            "title": title,
            "description": "Benchmark-created listing.",
            "attributes": {"rooms": "2"},
            "publish": False,
        },
    )
    resp.raise_for_status()
    listing_id: str = resp.json()["id"]
    return listing_id


async def interactive_listing_publish(
    client: httpx.AsyncClient, *, base_url: str, bearer_token: str, listing_id: str
) -> None:
    """NFR-PERF-002. `POST /listings/{id}/status` action=PUBLISH."""
    resp = await client.post(
        f"{base_url}/api/v1/listings/{listing_id}/status",
        headers={"Authorization": f"Bearer {bearer_token}"},
        json={"action": "PUBLISH"},
    )
    resp.raise_for_status()


async def interactive_banner_serve(
    client: httpx.AsyncClient, *, base_url: str, slot_key: str
) -> None:
    """NFR-PERF-002. `GET /banners/serve` -- public. Scoped down (see `README.md`): no banner
    campaign is seeded (would need a real placement-slot + creative + entitlement pipeline), so
    this call is expected to return an empty/no-serve response, not an error -- it still measures
    the operation's real latency floor (slot resolution + targeting evaluation with zero eligible
    campaigns), just not the fully-loaded-inventory case."""
    resp = await client.get(f"{base_url}/api/v1/banners/serve", params={"slotKey": slot_key})
    resp.raise_for_status()
