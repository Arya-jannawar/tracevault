"""Redis connector for the registered answer cache.

Redis is never authoritative: every entry is mirrored in the registry
(cache_entries + artifacts) and every hit is validated against PostgreSQL.
"""
from __future__ import annotations

import redis

from ..config import Settings
from .base import ConnectorOutcome, wrap_unavailable


class RedisConnector:
    def __init__(self, settings: Settings) -> None:
        self._client = redis.Redis.from_url(
            settings.redis_url, decode_responses=True, socket_timeout=3,
            socket_connect_timeout=3,
        )

    def health(self) -> bool:
        try:
            return bool(self._client.ping())
        except Exception:
            return False

    def get_json(self, key: str) -> dict | None:
        try:
            raw = self._client.get(key)
            return None if raw is None else __import__("json").loads(raw)
        except Exception as exc:  # noqa: BLE001
            raise wrap_unavailable(exc, "redis") from exc

    def set_json(self, key: str, value: dict, ttl_seconds: int) -> ConnectorOutcome:
        try:
            self._client.set(key, __import__("json").dumps(value), ex=ttl_seconds)
            return ConnectorOutcome(ok=True, acknowledged=True, detail="stored")
        except Exception as exc:  # noqa: BLE001
            return ConnectorOutcome(ok=False, acknowledged=False,
                                    error_code="redis_set_failed",
                                    detail=wrap_unavailable(exc, "redis").message)

    def delete(self, keys: list[str]) -> ConnectorOutcome:
        if not keys:
            return ConnectorOutcome(ok=True, acknowledged=True, detail="noop")
        try:
            self._client.delete(*keys)
            return ConnectorOutcome(ok=True, acknowledged=True, detail="deleted")
        except Exception as exc:  # noqa: BLE001
            return ConnectorOutcome(ok=False, acknowledged=False,
                                    error_code="redis_delete_failed",
                                    detail=wrap_unavailable(exc, "redis").message)
