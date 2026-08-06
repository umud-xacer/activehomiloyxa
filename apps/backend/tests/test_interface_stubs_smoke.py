"""Every module's interfaces/ package must actually import and construct at runtime, not just
pass mypy statically -- this is what catches Pydantic forward-ref / alias / union-type mistakes
that static analysis alone would miss (P-01 validation checklist: "every interface stub ...
contains zero business logic").

Builds a minimal valid instance of every DTO in every module by inspecting its Pydantic fields
and supplying the smallest value each annotation accepts, then round-trips it through
`model_dump(by_alias=True)` -> `model_validate` to prove the camelCase wire alias is consistent.
"""

from __future__ import annotations

import importlib
import types
import typing
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Literal, get_args, get_origin
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel

MODULES = [
    "identity",
    "profiles",
    "catalog",
    "configuration",
    "search",
    "media",
    "messaging",
    "billing",
    "ads",
    "notifications",
    "moderation",
    "admin",
    "analytics",
]
# `ads` has zero DTOs by design -- it has no v1 OpenAPI operations to derive any from (see
# apps/backend/src/ads/interfaces/ports.py docstring) -- so it's excluded from the
# every-DTO-round-trips test but still covered by the interfaces-package-imports test above.
MODULES_WITH_DTOS = [m for m in MODULES if m != "ads"]


def _unwrap_optional(annotation: Any) -> tuple[Any, bool]:
    if get_origin(annotation) in (typing.Union, types.UnionType):
        args = [a for a in get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return args[0], True
    return annotation, False


def _minimal_value(annotation: Any) -> Any:
    annotation, _ = _unwrap_optional(annotation)
    origin = get_origin(annotation)

    if annotation is str:
        return "x"
    if annotation is int:
        return 1
    if annotation is float:
        return 1.0
    if annotation is bool:
        return True
    if annotation is UUID:
        return uuid4()
    if annotation is datetime:
        return datetime.now(UTC)
    if annotation is Decimal:
        return Decimal("1.00")
    if annotation is Any or annotation is None:
        return {}

    if origin is Literal:
        return get_args(annotation)[0]
    if origin in (list, list.__class__) or annotation is list:
        return []
    if origin is dict or annotation is dict:
        return {}

    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return next(iter(annotation))
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return _minimal_instance(annotation)

    pytest.fail(f"test helper doesn't know how to build a value for annotation {annotation!r}")


def _minimal_instance(cls: type[BaseModel]) -> BaseModel:
    # `model_fields[...].annotation` only reflects fully-resolved types (e.g. `list[FormSection]`
    # rather than a raw `ForwardRef`) once the model has rebuilt its schema; with `from __future__
    # import annotations`, a class referencing another defined later in the same file may not have
    # triggered that rebuild yet at introspection time. Force it before reading annotations.
    cls.model_rebuild(force=True)
    kwargs: dict[str, Any] = {}
    for field_name, field in cls.model_fields.items():
        if not field.is_required():
            continue
        kwargs[field_name] = _minimal_value(field.annotation)
    return cls(**kwargs)


@pytest.mark.parametrize("module_name", MODULES)
def test_FR_CONTRACT_001_interfaces_package_imports(module_name: str) -> None:
    """# enforces AIR-02: interfaces/ is the module's sole importable surface, and it must
    actually be importable."""
    mod = importlib.import_module(f"{module_name}.interfaces")
    assert mod.__all__, f"{module_name}.interfaces.__all__ is empty"


@pytest.mark.parametrize("module_name", MODULES_WITH_DTOS)
def test_FR_CONTRACT_002_every_dto_constructs_and_round_trips(module_name: str) -> None:
    dto_module = importlib.import_module(f"{module_name}.interfaces.dto")
    dto_classes = [
        obj
        for name, obj in vars(dto_module).items()
        if isinstance(obj, type)
        and issubclass(obj, BaseModel)
        and obj.__module__ == dto_module.__name__
    ]
    assert dto_classes, f"{module_name}.interfaces.dto defines no DTO classes"

    for cls in dto_classes:
        instance = _minimal_instance(cls)
        wire = instance.model_dump(by_alias=True, mode="json")
        rebuilt = cls.model_validate(wire)
        assert rebuilt == instance, (
            f"{cls.__name__} does not round-trip through its camelCase alias"
        )
