"""Verification harness for Active Home. Lives outside the repo (P-VERIFY Rule 1)."""

from __future__ import annotations

import json
import os
import subprocess
import uuid

import httpx

BASE = os.environ.get("AH_BASE", "http://127.0.0.1:8100/api/v1")
PG = [
    "psql",
    "-h",
    "localhost",
    "-U",
    "active_home",
    "-d",
    "active_home_verify",
    "-qtA",
]
RESULTS: list[dict] = []


def sql(q: str) -> str:
    env = dict(os.environ, PGPASSWORD="<redacted-local-dev-password>")
    return subprocess.run(
        [*PG, "-c", q], capture_output=True, text=True, env=env
    ).stdout.strip()


class Actor:
    """One logged-in (or anonymous) API client."""

    def __init__(self, label: str):
        self.label = label
        # DEF-003: the API drops the keep-alive connection after every ExceptionMapper-produced
        # error response, so pooled connections fail on alternate requests. Disable keep-alive
        # here so the harness can keep verifying everything else.
        self.c = httpx.Client(
            base_url=BASE,
            timeout=30.0,
            follow_redirects=False,
            limits=httpx.Limits(max_keepalive_connections=0),
        )
        self.user_id: str | None = None

    def req(self, method: str, path: str, **kw):
        hdrs = kw.pop("headers", {}) or {}
        if kw.pop("idem", False):
            hdrs["Idempotency-Key"] = str(uuid.uuid4())
        return self.c.request(method, path, headers=hdrs, **kw)

    def get(self, p, **k):
        return self.req("GET", p, **k)

    def post(self, p, **k):
        return self.req("POST", p, **k)

    def put(self, p, **k):
        return self.req("PUT", p, **k)

    def patch(self, p, **k):
        return self.req("PATCH", p, **k)

    def delete(self, p, **k):
        return self.req("DELETE", p, **k)

    def register_login(self, email: str, name: str, password: str = "Str0ng!Passw0rd"):
        reg = self.c.post(
            "/auth/register/email",
            json={"email": email, "password": password, "displayName": name},
        )
        import time as _t

        for _ in range(20):  # registration is async (202 before commit) -- see DEF on the race
            r = self.c.post(
                "/auth/login/email", json={"email": email, "password": password}
            )
            if r.status_code == 200:
                break
            _t.sleep(0.25)
        if r.status_code != 200:
            raise RuntimeError(
                f"register_login({email}) failed: register={reg.status_code} {reg.text[:200]} "
                f"login={r.status_code} {r.text[:200]}"
            )
        data = r.json()
        self.user_id = data["account"]["id"]
        # The session cookie is issued with Secure, which httpx will not replay over plain
        # HTTP. Use the documented Bearer path for native clients instead.
        self.c.headers["Authorization"] = f"Bearer {data['sessionToken']}"
        return self


def check(cid: str, doc: str, expected: str, resp, ok, note: str = ""):
    """Record one doc-cited check. `ok` may be a bool or a callable(resp)->bool."""
    if callable(ok):
        try:
            passed = bool(ok(resp))
        except Exception as exc:  # noqa: BLE001
            passed = False
            note = f"{note} [predicate raised {type(exc).__name__}: {exc}]"
    else:
        passed = bool(ok)
    if isinstance(resp, httpx.Response):
        body = resp.text[:600]
        status = resp.status_code
    else:
        body = str(resp)[:600]
        status = None
    RESULTS.append(
        {
            "id": cid,
            "doc": doc,
            "expected": expected,
            "status": status,
            "passed": passed,
            "observed": body,
            "note": note,
        }
    )
    print(f"{'PASS' if passed else 'FAIL'}  {cid:22} [{doc}] {status} {note}")
    return passed


def items(resp):
    """Both bare-array and CursorPage envelopes appear across the API."""
    try:
        b = resp.json()
    except Exception:  # noqa: BLE001
        return []
    return b if isinstance(b, list) else b.get("items", [])


def dump(path: str):
    with open(path, "w") as fh:
        json.dump(RESULTS, fh, indent=1)
    n = sum(1 for r in RESULTS if r["passed"])
    print(f"\n{n}/{len(RESULTS)} checks passed -> {path}")
