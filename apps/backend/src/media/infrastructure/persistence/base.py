"""The `media` schema's declarative base (Physical DB Sec 2.6: schema-per-module,
`backbone.persistence.make_module_base`)."""

from __future__ import annotations

from backbone.persistence import make_module_base

MediaBase = make_module_base("media")
