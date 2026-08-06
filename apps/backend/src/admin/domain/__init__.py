"""admin/domain -- the operator work-session context ONLY. No marketplace aggregate is defined
here, or ever will be (DDD Sec 5.12) -- `test_composition_only.py` inspects this package
directly and fails deliberately if a second entity type is ever added.
"""

from __future__ import annotations

from admin.domain.operator_session import OperatorSessionContext

__all__ = ["OperatorSessionContext"]
