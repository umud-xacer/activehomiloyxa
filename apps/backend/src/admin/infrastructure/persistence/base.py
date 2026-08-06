"""`AdminBase` -- admin's own PostgreSQL schema, per `backbone.persistence.make_module_base`
(Physical DB Sec 13: "one MetaData per module with schema=\"<module>\"")."""

from __future__ import annotations

from backbone.persistence import make_module_base

AdminBase = make_module_base("admin")
