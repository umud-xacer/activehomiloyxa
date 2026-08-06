"""The `messaging` schema's declarative base (Physical DB Sec 2/13: schema-per-module,
`backbone.persistence.make_module_base`)."""

from __future__ import annotations

from backbone.persistence import make_module_base

MessagingBase = make_module_base("messaging")
