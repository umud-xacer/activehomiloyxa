"""The `ads` schema's declarative base (Physical DB Sec 2/13: schema-per-module,
`backbone.persistence.make_module_base`)."""

from __future__ import annotations

from backbone.persistence import make_module_base

AdsBase = make_module_base("ads")
