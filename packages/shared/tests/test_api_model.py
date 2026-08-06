"""active_home_shared.CamelModel -- the camelCase wire-alias base every DTO in every module's
interfaces/dto.py inherits from."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from active_home_shared import CamelModel


class _Example(CamelModel):
    owner_user_id: str
    created_at: str


def test_camel_model_aliases_snake_case_to_camel_case() -> None:
    example = _Example(owner_user_id="u1", created_at="t1")
    assert example.model_dump(by_alias=True) == {"ownerUserId": "u1", "createdAt": "t1"}


def test_camel_model_accepts_either_alias_on_input() -> None:
    from_camel = _Example.model_validate({"ownerUserId": "u1", "createdAt": "t1"})
    from_snake = _Example(owner_user_id="u1", created_at="t1")
    assert from_camel == from_snake


def test_camel_model_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        _Example.model_validate({"ownerUserId": "u1", "createdAt": "t1", "extra": "nope"})
