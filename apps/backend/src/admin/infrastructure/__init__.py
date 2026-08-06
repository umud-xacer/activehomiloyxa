"""admin/infrastructure -- the operator-session repository only. No adapters for other modules'
ports are declared here -- admin's application layer imports each owning module's real
`interfaces/` port type directly (e.g. `profiles.interfaces.ports.VerificationPort`) and the
composition root wires the REAL, already-existing concrete implementation those modules'
own routers already use; there is no second adapter for admin to build or own."""

from __future__ import annotations

from admin.infrastructure.persistence import AdminBase, SqlalchemyOperatorSessionRepository

__all__ = ["AdminBase", "SqlalchemyOperatorSessionRepository"]
