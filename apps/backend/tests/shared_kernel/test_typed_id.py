"""TypedId -- immutable, self-validating, and nominally distinct per concept even for the same
underlying UUID (Database Architecture Sec 10: "wrapped in the strongly-typed identifier VOs of
the shared kernel (UserId, ListingId, ...)")."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from shared_kernel import ListingId, TypedId, UserId


def test_keyword_construction() -> None:
    raw = uuid4()
    assert UserId(value=raw).value == raw


def test_rejects_non_uuid_value() -> None:
    with pytest.raises(ValidationError):
        UserId(value="not-a-uuid")  # type: ignore[arg-type]


def test_str_is_the_raw_uuid_string() -> None:
    raw = uuid4()
    assert str(UserId(value=raw)) == str(raw)


def test_same_type_same_value_are_equal_and_hash_equal() -> None:
    raw = uuid4()
    assert UserId(value=raw) == UserId(value=raw)
    assert hash(UserId(value=raw)) == hash(UserId(value=raw))


def test_I08_different_concept_same_value_are_not_equal() -> None:
    """# enforces: a value of the wrong kind cannot be substituted for another, even at runtime,
    not just under mypy."""
    raw = uuid4()
    assert UserId(value=raw) != ListingId(value=raw)  # type: ignore[comparison-overlap]


def test_different_type_same_value_distinguished_in_a_set() -> None:
    raw = uuid4()
    assert {UserId(value=raw), ListingId(value=raw), UserId(value=raw)} == {
        UserId(value=raw),
        ListingId(value=raw),
    }
    assert len({UserId(value=raw), ListingId(value=raw), UserId(value=raw)}) == 2


def test_is_immutable() -> None:
    uid = UserId(value=uuid4())
    with pytest.raises(ValidationError):
        uid.value = uuid4()  # type: ignore[misc]


def test_concrete_ids_are_typed_id_subclasses() -> None:
    assert issubclass(UserId, TypedId)
    assert issubclass(ListingId, TypedId)


def test_uuid_type_is_enforced() -> None:
    uid = UserId(value=uuid4())
    assert isinstance(uid.value, UUID)
