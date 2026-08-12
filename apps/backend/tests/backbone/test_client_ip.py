"""Unit tests for `backbone.net.resolve_client_ip`'s header-precedence chain (Cloudflare's
`CF-Connecting-IP` first, nginx's own `X-Real-IP` second, TCP-peer fallback last) -- see that
function's own docstring for why each step exists."""

from __future__ import annotations

from starlette.datastructures import Headers

from backbone.net import resolve_client_ip


def test_prefers_cf_connecting_ip_over_everything() -> None:
    headers = Headers({"cf-connecting-ip": "1.1.1.1", "x-real-ip": "2.2.2.2"})
    assert resolve_client_ip(headers, fallback_host="3.3.3.3") == "1.1.1.1"


def test_falls_back_to_x_real_ip_when_no_cf_header() -> None:
    headers = Headers({"x-real-ip": "2.2.2.2"})
    assert resolve_client_ip(headers, fallback_host="3.3.3.3") == "2.2.2.2"


def test_falls_back_to_tcp_peer_when_no_headers_present() -> None:
    headers = Headers({})
    assert resolve_client_ip(headers, fallback_host="3.3.3.3") == "3.3.3.3"


def test_returns_unknown_when_nothing_is_available() -> None:
    headers = Headers({})
    assert resolve_client_ip(headers, fallback_host=None) == "unknown"


def test_never_trusts_x_forwarded_for() -> None:
    """`X-Forwarded-For`'s first hop is attacker-controllable (nginx only appends, never
    replaces) -- deliberately never read."""
    headers = Headers({"x-forwarded-for": "9.9.9.9"})
    assert resolve_client_ip(headers, fallback_host="3.3.3.3") == "3.3.3.3"


def test_strips_whitespace_from_header_values() -> None:
    headers = Headers({"cf-connecting-ip": "  1.1.1.1  "})
    assert resolve_client_ip(headers, fallback_host=None) == "1.1.1.1"
