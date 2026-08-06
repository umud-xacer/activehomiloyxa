"""QG-06 (Playbook Sec 16): contracts/openapi.yaml is well-formed OpenAPI 3.1, every $ref
resolves, and no OAS-3.0-style `nullable:` keyword has crept back in (OAS 3.1 uses JSON
Schema's native `type: [X, "null"]` instead -- the whole spec already uses that idiom
throughout, so a `nullable:` key appearing anywhere is a regression, not a style choice).

Usage: python tools/validate_openapi.py contracts/openapi.yaml
"""

from __future__ import annotations

import sys

import yaml
from openapi_spec_validator import validate


def check_no_legacy_nullable(raw_text: str) -> list[str]:
    problems = []
    for lineno, line in enumerate(raw_text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("nullable:") or stripped.startswith("nullable :"):
            problems.append(f"line {lineno}: legacy OAS-3.0 `nullable:` keyword: {stripped!r}")
    return problems


def main(path: str) -> int:
    with open(path, encoding="utf-8") as f:
        raw_text = f.read()

    spec = yaml.safe_load(raw_text)

    # well-formedness + $ref resolution (raises on any unresolved $ref or schema violation)
    validate(spec)
    print(f"OK: {path} is well-formed OpenAPI 3.1 and every $ref resolves.")

    nullable_problems = check_no_legacy_nullable(raw_text)
    if nullable_problems:
        print('FAILED: legacy `nullable:` usage found (OAS 3.1 uses `type: [X, "null"]`):')
        for p in nullable_problems:
            print(f"  - {p}")
        return 1
    print("OK: no legacy `nullable:` usage.")
    return 0


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "contracts/openapi.yaml"
    raise SystemExit(main(path))
