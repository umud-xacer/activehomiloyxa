"""The `configuration` schema's declarative base (Physical DB Sec 2.4: schema-per-module,
`backbone.persistence.make_module_base`). One `MetaData`, one call -- every ORM class in this
module maps into it."""

from __future__ import annotations

from backbone.persistence import make_module_base

ConfigurationBase = make_module_base("configuration")
