"""The real client IP behind Cloudflare + nginx, shared by every module that needs to scope a
Redis counter (rate limiting, brute-force lockout) per visitor rather than per TCP peer.

Originally `identity.interfaces.routers._client_ip` (built while adding login-lockout, NFR-SEC
brute-force protection) -- moved here once `configuration`'s owner-admin-access oracle and the
global rate-limit middleware needed the exact same resolution, and `backbone` (unlike any bounded
context) is the one place every module's `interfaces`/`infrastructure` layer is allowed to import
from (`tools/importlinter.cfg`'s `backbone-imports-only-shared-kernel` contract) without creating
a forbidden cross-module edge.
"""

from __future__ import annotations

from starlette.datastructures import Headers


def resolve_client_ip(headers: Headers, *, fallback_host: str | None) -> str:
    """The real client IP, not the TCP peer -- production runs behind nginx on the same host
    (`deployment/nginx/activehome.conf` proxies to `127.0.0.1:8000`), and uvicorn is started
    without `--proxy-headers` (`deployment/systemd/activehome-api.service`), so the TCP peer seen
    by the app is always `127.0.0.1` there regardless of who's actually asking.

    `CF-Connecting-IP` is checked first: `activehome.uz`'s DNS is Cloudflare-proxied (CLAUDE.md
    "Joriy Holat"), so the connection nginx actually sees is Cloudflare's edge IP, not the
    visitor's -- `X-Real-IP` (nginx's own `proxy_set_header X-Real-IP $remote_addr`) reflects
    THAT, and Cloudflare's edge IP for a given visitor varies request to request (different edge
    nodes/load balancing), which would silently defeat any IP-scoped throttle/lockout even after
    the `X-Real-IP` fallback below. Cloudflare itself sets `CF-Connecting-IP` from the real TCP
    connection on every proxied request, which nginx passes through unmodified (no
    `proxy_set_header` overrides or hides it).

    Residual gap, not fully closed here: nginx's `server_name` also matches the bare EC2 IP, so
    direct non-Cloudflare access is possible today, and a request arriving that way COULD carry a
    spoofed `CF-Connecting-IP` header nothing here can distinguish from a real one. Properly
    closing it means either an AWS security-group rule restricting :80/:443 to Cloudflare's
    published IP ranges, or nginx's `ngx_http_realip_module` -- real infrastructure changes, out
    of scope for an application-code fix.

    `X-Real-IP` is the second fallback -- still correct for any future non-Cloudflare topology (a
    different CDN, or none) as long as nginx remains the sole ingress. `X-Forwarded-For`'s first
    hop is deliberately never used: nginx's `$proxy_add_x_forwarded_for` appends to whatever the
    client already sent, so an attacker-supplied first entry survives untouched. Falls back to
    `fallback_host` (the TCP peer) for local dev (no nginx/Cloudflare in front) and any other
    topology where none of the above headers are present."""
    cf_connecting_ip = headers.get("cf-connecting-ip")
    if cf_connecting_ip:
        return cf_connecting_ip.strip()
    real_ip = headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return fallback_host or "unknown"
