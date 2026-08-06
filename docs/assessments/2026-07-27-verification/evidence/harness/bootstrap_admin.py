"""Bootstrap operator accounts. No API path exists to assign the FIRST administrator
(recorded as a defect), so the role assignment is a direct INSERT."""

import sys
import time

import httpx

from ah import sql

BASE = "http://127.0.0.1:8100/api/v1"
c = httpx.Client(base_url=BASE, timeout=30, limits=httpx.Limits(max_keepalive_connections=0))


def ensure(email: str, name: str, role: str) -> str:
    c.post(
        "/auth/register/email",
        json={"email": email, "password": "Str0ng!Passw0rd", "displayName": name},
    )
    for _ in range(20):
        r = c.post("/auth/login/email", json={"email": email, "password": "Str0ng!Passw0rd"})
        if r.status_code == 200:
            break
        time.sleep(0.25)
    else:
        sys.exit(f"could not log in {email}: {r.status_code} {r.text[:200]}")
    uid = r.json()["account"]["id"]
    head, ver = sql(
        f"select h.id||' '||h.current_version_id from configuration.role_definition h "
        f"where h.code='{role}'"
    ).split()
    sql(
        "insert into identity.role_assignment "
        "(id, account_id, role_definition_head_id, role_definition_version_id, role_code, "
        " acting_profile_id, assigned_at, assigned_by) "
        f"select gen_random_uuid(), '{uid}', '{head}', '{ver}', '{role}', NULL, now(), '{uid}' "
        "where not exists (select 1 from identity.role_assignment "
        f"  where account_id='{uid}' and role_code='{role}')"
    )
    print(f"{email} -> {uid} [{role}]")
    return r.json()["sessionToken"]


if __name__ == "__main__":
    t1 = ensure("maker.admin@example.invalid", "Maker Admin", "super-admin")
    t2 = ensure("checker.admin@example.invalid", "Checker Admin", "super-admin")
    with open("/home/ameer/.claude/jobs/06393b27/tmp/admin_tokens.txt", "w") as fh:
        fh.write(f"{t1}\n{t2}\n")
    r = httpx.get(
        f"{BASE}/admin/users", headers={"Authorization": f"Bearer {t1}"}, timeout=30
    )
    print("GET /admin/users as super-admin ->", r.status_code, r.text[:200])
