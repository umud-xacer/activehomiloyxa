"""Redis connection URL assembly (Infra Sec 11 environment-variable convention), mirroring
`engine.database_url()`. Not named `redis.py`: while Python 3's absolute-import default means a
nested module of that name would not actually collide with the top-level `redis` package, the
name would still read as ambiguous next to every `import redis` in this same file.
"""

from __future__ import annotations

import os

from backbone.persistence.env import MissingInfraConfigError, required_env


def redis_url() -> str:
    host = required_env("REDIS_HOST")
    port = os.environ.get("REDIS_PORT", "6379")
    return f"redis://{host}:{port}/0"


__all__ = ["MissingInfraConfigError", "redis_url"]
