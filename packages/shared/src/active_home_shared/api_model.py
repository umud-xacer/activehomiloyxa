"""CamelModel -- the base Pydantic model for HTTP-facing DTOs (business-logic-free, CLAUDE.md
"packages/shared ... types, error envelope, logging"). `contracts/openapi.yaml` field names are
camelCase (e.g. `traceId`, `ownerUserId`); DTOs are written Pythonic snake_case and rely on this
base for the camelCase wire alias, so a DTO's Python attribute name and its JSON key never have
to be typed twice or drift apart by hand.

Not used by `shared_kernel` value objects (`LocalizedText`, `Money`, `GeoLocation`): their JSON
field names either already match their Python names one-for-one, or -- `LocalizedText`'s
`uz_latn`/`uz_cyrl` -- are locale codes that must NOT be camelCased (`to_camel("uz_latn")` would
wrongly produce `uzLatn`). Applying this generator there would silently break those contracts.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )
