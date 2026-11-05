"""Test fixtures.

* Unit tests run on SQLite with DETERMINISTIC TEST ADAPTERS (FakeQdrant,
  FakeRedis, deterministic embeddings/LLM) — clearly identified; they never
  stand in for real-service results.
* Integration tests (marker `integration`) exercise REAL PostgreSQL, Qdrant
  and Redis via Docker and are skipped when services are unavailable.
  A skipped integration check is NOT a pass.
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("SESSION_SECRET", "test-secret-not-for-production")
os.environ.setdefault("EMBEDDING_PROVIDER", "deterministic")
os.environ.setdefault("LLM_PROVIDER", "deterministic")
os.environ.setdefault("SEED_ON_START", "false")
os.environ.setdefault("ENABLE_SELECTIVE_REPAIR", "true")


# ------------------------------------------------------------------ fakes
class FakeQdrant:
    """In-memory deterministic stand-in for tests ONLY."""

    def __init__(self) -> None:
        self.points: dict[str, dict] = {}
        self.cache_points: dict[str, dict] = {}
        self.available = True

    def health(self) -> bool:
        return self.available

    def ensure_collection(self) -> None:
        pass

    def ensure_cache_collection(self) -> None:
        pass

    def upsert_points(self, points: list[dict], *, wait: bool = True):
        if not self.available:
            from app.connectors.base import ConnectorOutcome

            return ConnectorOutcome(False, acknowledged=False,
                                     error_code="qdrant_unavailable")
        for p in points:
            self.points[p["id"]] = {"vector": p["vector"], "payload": p["payload"]}
        from app.connectors.base import ConnectorOutcome

        return ConnectorOutcome(True, acknowledged=True, detail="upserted")

    def delete_points(self, point_ids: list[str], *, wait: bool = True):
        if not self.available:
            from app.connectors.base import ConnectorOutcome

            return ConnectorOutcome(False, acknowledged=False,
                                    error_code="qdrant_unavailable")
        for pid in point_ids:
            self.points.pop(pid, None)
        from app.connectors.base import ConnectorOutcome

        return ConnectorOutcome(True, acknowledged=True, detail="deleted")

    def retrieve_points(self, point_ids: list[str], with_payload: bool = True):
        if not self.available:
            from app.errors import ConnectorUnavailable

            raise ConnectorUnavailable("qdrant unavailable (fake)")
        return [{"id": pid, "payload": self.points[pid]["payload"]}
                for pid in point_ids if pid in self.points]

    def search(self, vector: list[float], *, limit: int = 8,
               workspace_id: int | None = None,
               document_ids: list[str] | None = None):
        if not self.available:
            from app.errors import ConnectorUnavailable

            raise ConnectorUnavailable("qdrant unavailable (fake)")

        def cos(a, b):
            dot = sum(x * y for x, y in zip(a, b))
            na = math.sqrt(sum(x * x for x in a)) or 1.0
            nb = math.sqrt(sum(x * x for x in b)) or 1.0
            return dot / (na * nb)

        scored = []
        for pid, rec in self.points.items():
            payload = rec["payload"]
            if workspace_id is not None and payload.get("workspace_id") != workspace_id:
                continue
            if document_ids and payload.get("document_id") not in document_ids:
                continue
            scored.append({"id": pid, "score": cos(vector, rec["vector"]),
                           "payload": payload})
        scored.sort(key=lambda h: -h["score"])
        return scored[:limit]

    def upsert_cache_query(self, point_id: str, vector: list[float], payload: dict):
        self.cache_points[point_id] = {"vector": vector, "payload": payload}
        from app.connectors.base import ConnectorOutcome

        return ConnectorOutcome(True, acknowledged=True, detail="cached")

    def search_cache_queries(self, vector: list[float], *, limit: int = 3,
                             workspace_id: int):
        return []

    def delete_cache_query_points(self, point_ids: list[str]):
        for pid in point_ids:
            self.cache_points.pop(pid, None)
        from app.connectors.base import ConnectorOutcome

        return ConnectorOutcome(True, acknowledged=True, detail="deleted")


class FakeRedis:
    """In-memory deterministic stand-in for tests ONLY."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.available = True

    def health(self) -> bool:
        return self.available

    def get_json(self, key: str):
        if not self.available:
            from app.errors import ConnectorUnavailable

            raise ConnectorUnavailable("redis unavailable (fake)")
        import json

        raw = self.store.get(key)
        return None if raw is None else json.loads(raw)

    def set_json(self, key: str, value: dict, ttl_seconds: int):
        if not self.available:
            from app.connectors.base import ConnectorOutcome

            return ConnectorOutcome(False, acknowledged=False,
                                    error_code="redis_unavailable")
        import json

        self.store[key] = json.dumps(value)
        from app.connectors.base import ConnectorOutcome

        return ConnectorOutcome(True, acknowledged=True, detail="stored")

    def delete(self, keys: list[str]):
        if not self.available:
            from app.connectors.base import ConnectorOutcome

            return ConnectorOutcome(False, acknowledged=False,
                                    error_code="redis_unavailable")
        for k in keys:
            self.store.pop(k, None)
        from app.connectors.base import ConnectorOutcome

        return ConnectorOutcome(True, acknowledged=True, detail="deleted")


# ------------------------------------------------------------------ fixtures
@pytest.fixture()
def settings():
    from app.config import get_settings

    get_settings.cache_clear()
    s = get_settings()
    yield s
    get_settings.cache_clear()


@pytest.fixture()
def db(settings):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.models import Base

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def workspace(db):
    from app.fence import get_or_create_default_workspace

    return get_or_create_default_workspace(db, "test")


@pytest.fixture()
def fake_qdrant():
    return FakeQdrant()


@pytest.fixture()
def fake_redis():
    return FakeRedis()


@pytest.fixture()
def adapters(settings):
    from app.rag.embeddings import DeterministicEmbedding
    from app.rag.llm import DeterministicLLM

    return DeterministicEmbedding(settings.embedding_dim), DeterministicLLM()
