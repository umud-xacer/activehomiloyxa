"""P-20: the comprehensive, mechanical default-deny sweep (Security Sec 4.2 Gate 1: "Authenticated?
... else 401"; validation checklist: "default-deny holds everywhere including /admin"). Derives
its own parametrization DIRECTLY from `contracts/openapi.yaml` at collection time (not a hand-kept
copy) -- an operation is "secured" unless it declares `security: []` (the same override FastAPI's
own OpenAPI generator would show), so a newly added, un-annotated endpoint is swept automatically
and a newly added PUBLIC endpoint must say so explicitly in the contract, not by omission from a
hand-maintained list here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_OPENAPI_PATH = _REPO_ROOT / "contracts" / "openapi.yaml"


@dataclass(frozen=True)
class SecuredOperation:
    id: str
    verb: str
    path: str
    path_params: tuple[str, ...]
    has_body: bool


def secured_operations() -> list[SecuredOperation]:
    """Every `contracts/openapi.yaml` operation that requires `sessionCookie` (the top-level
    default) and does not override it with `security: []`."""
    spec = cast(dict[str, Any], yaml.safe_load(_OPENAPI_PATH.read_text(encoding="utf-8")))
    top_level_security = spec.get("security")
    operations: list[SecuredOperation] = []
    for path, methods in spec["paths"].items():
        path_params = tuple(re.findall(r"\{([^}]+)\}", path))
        for verb, operation in methods.items():
            if not isinstance(operation, dict) or "operationId" not in operation:
                continue
            operation_security = operation.get("security", top_level_security)
            if operation_security == []:
                continue
            operations.append(
                SecuredOperation(
                    id=operation["operationId"],
                    verb=verb.upper(),
                    path=path,
                    path_params=path_params,
                    has_body="requestBody" in operation,
                )
            )
    return operations


def resolved_path(operation: SecuredOperation) -> str:
    """Substitutes a syntactically-valid placeholder (a random UUID) for every path parameter --
    the exact value never matters here, since an unauthenticated caller must be rejected before
    any path-parameter-specific lookup could even return a real answer."""
    path = operation.path
    for param in operation.path_params:
        path = path.replace(f"{{{param}}}", str(uuid4()))
    return path
