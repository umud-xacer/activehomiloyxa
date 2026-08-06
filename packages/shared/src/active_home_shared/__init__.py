"""active_home_shared -- cross-cutting, business-logic-free utilities (CLAUDE.md).

MUST NOT contain domain logic or a module's internals (Playbook Sec 2 "Shared-code rule").
"""

from active_home_shared.api_model import CamelModel

__all__ = ["CamelModel"]
