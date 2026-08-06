"""QG-04 / COV-01 (Playbook Sec 11): fail if any module's domain/ or application/ layer is
below the 90% line-coverage floor. Reads coverage.json produced by:
    coverage json --rcfile=tools/coverage.ini -o coverage.json

Usage: python tools/check_domain_coverage.py coverage.json
"""

from __future__ import annotations

import json
import sys

DOMAIN_APP_FLOOR = 90.0


def main(coverage_json_path: str) -> int:
    with open(coverage_json_path, encoding="utf-8") as f:
        data = json.load(f)

    failures: list[str] = []
    for file_path, file_data in data.get("files", {}).items():
        normalized = file_path.replace("\\", "/")
        if "/domain/" not in normalized and "/application/" not in normalized:
            continue
        percent = file_data["summary"]["percent_covered"]
        if percent < DOMAIN_APP_FLOOR:
            failures.append(f"{normalized}: {percent:.2f}% < {DOMAIN_APP_FLOOR}%")

    if failures:
        print("QG-04 FAILED: domain/application coverage below the 90% floor:")
        for line in failures:
            print(f"  - {line}")
        return 1

    print("QG-04 OK: no domain/application file is below the 90% floor.")
    return 0


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "coverage.json"
    raise SystemExit(main(path))
