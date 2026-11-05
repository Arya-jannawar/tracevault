"""Qdrant connector over the REST API (httpx).

REST covers everything we need (collection management, upsert, delete-points,
search, retrieve) and avoids pulling gRPC build dependencies. Deleting a point
deletes the whole point *including its payload*, per Qdrant's point model.
API reference: https://api.qdrant.tech/api-reference/points/delete-points
"""
from __future__ import annotations

import httpx

from ..config import Settings
from .base import ConnectorOutcome, wrap_unavailable

_TIMEOUT = httpx.Timeout(10.0, connect=3.0)


class QdrantConnector:
    def __init__(self, settings: Settings) -> None:
        self._base = settings.qdrant_url.rstrip("/")
        self._collection = settings.qdrant_collection
        self._dim = settings.embedding_dim

    # ------------------------------------------------------------- health
    def health(self) -> bool:
        try:
            r = httpx.get(f"{self._base}/healthz", timeout=2.0)
            return r.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------- collection
    def ensure_collection(self) -> None:
        try:
            r = httpx.get(f"{self._base}/collections/{self._collection}", timeout=_TIMEOUT)
            if r.status_code == 200:
                return
            body = {"vectors": {"size": self._dim, "distance": "Cosine"}}
            r = httpx.put(f"{self._base}/collections/{self._collection}",
                          json=body, timeout=_TIMEOUT)
            r.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            raise wrap_unavailable(exc, "qdrant") from exc

    def ensure_cache_collection(self) -> None:
        name = f"{self._collection}-cacheq"
        try:
            r = httpx.get(f"{self._base}/collections/{name}", timeout=_TIMEOUT)
            if r.status_code == 200:
                return
            r = httpx.put(f"{self._base}/collections/{name}",
                          json={"vectors": {"size": self._dim, "distance": "Cosine"}},
                          timeout=_TIMEOUT)
            r.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            raise wrap_unavailable(exc, "qdrant") from exc

    # ------------------------------------------------------------- points
    def upsert_points(self, points: list[dict], *, wait: bool = True) -> ConnectorOutcome:
        """points: [{id, vector, payload}] — payload must carry workspace/document/
        artifact identifiers so retrieval can re-authorize against the registry."""
        try:
            r = httpx.put(
                f"{self._base}/collections/{self._collection}/points",
                json={"points": points, "wait": wait},
                timeout=_TIMEOUT,
            )
            r.raise_for_status()
            return ConnectorOutcome(ok=True, acknowledged=True, detail="upserted")
        except Exception as exc:  # noqa: BLE001
            return ConnectorOutcome(ok=False, acknowledged=False,
                                    error_code="qdrant_upsert_failed",
                                    detail=wrap_unavailable(exc, "qdrant").message)

    def delete_points(self, point_ids: list[str], *, wait: bool = True) -> ConnectorOutcome:
        """Delete full points (values + payload) by explicit IDs."""
        try:
            r = httpx.post(
                f"{self._base}/collections/{self._collection}/points/delete",
                json={"points": point_ids, "wait": wait},
                timeout=_TIMEOUT,
            )
            r.raise_for_status()
            return ConnectorOutcome(ok=True, acknowledged=True, detail="deleted")
        except Exception as exc:  # noqa: BLE001
            return ConnectorOutcome(ok=False, acknowledged=False,
                                    error_code="qdrant_delete_failed",
                                    detail=wrap_unavailable(exc, "qdrant").message)

    def retrieve_points(self, point_ids: list[str],
                        with_payload: bool = True) -> list[dict]:
        """Get points by explicit IDs (Qdrant 'look up points' API:
        POST /collections/{name}/points)."""
        try:
            r = httpx.post(
                f"{self._base}/collections/{self._collection}/points",
                json={"ids": point_ids, "with_payload": with_payload},
                timeout=_TIMEOUT,
            )
            r.raise_for_status()
            return r.json().get("result", [])
        except Exception as exc:  # noqa: BLE001
            raise wrap_unavailable(exc, "qdrant") from exc

    def search(self, vector: list[float], *, limit: int = 8,
               workspace_id: int | None = None,
               document_ids: list[str] | None = None) -> list[dict]:
        """Similarity search. Filter is a pre-filter only; authorization is
        ALWAYS re-checked against the registry before content is used."""
        must: list[dict] = []
        if workspace_id is not None:
            must.append({"key": "workspace_id", "match": {"value": workspace_id}})
        if document_ids:
            must.append({"key": "document_id",
                         "match": {"any": [str(d) for d in document_ids]}})
        body: dict = {"vector": vector, "limit": limit, "with_payload": True}
        if must:
            body["filter"] = {"must": must}
        try:
            r = httpx.post(
                f"{self._base}/collections/{self._collection}/points/search",
                json=body, timeout=_TIMEOUT,
            )
            r.raise_for_status()
            return r.json().get("result", [])
        except Exception as exc:  # noqa: BLE001
            raise wrap_unavailable(exc, "qdrant") from exc

    # ----------------------------------------------------- semantic cache index
    def upsert_cache_query(self, point_id: str, vector: list[float],
                           payload: dict) -> ConnectorOutcome:
        try:
            r = httpx.put(
                f"{self._base}/collections/{self._collection}-cacheq/points",
                json={"points": [{"id": point_id, "vector": vector,
                                  "payload": payload}], "wait": True},
                timeout=_TIMEOUT,
            )
            r.raise_for_status()
            return ConnectorOutcome(ok=True, acknowledged=True, detail="cached")
        except Exception as exc:  # noqa: BLE001
            return ConnectorOutcome(ok=False, acknowledged=False,
                                    error_code="qdrant_cache_upsert_failed",
                                    detail=wrap_unavailable(exc, "qdrant").message)

    def search_cache_queries(self, vector: list[float], *, limit: int = 3,
                             workspace_id: int) -> list[dict]:
        try:
            r = httpx.post(
                f"{self._base}/collections/{self._collection}-cacheq/points/search",
                json={"vector": vector, "limit": limit, "with_payload": True,
                      "filter": {"must": [{"key": "workspace_id",
                                           "match": {"value": workspace_id}}]}},
                timeout=_TIMEOUT,
            )
            r.raise_for_status()
            return r.json().get("result", [])
        except Exception as exc:  # noqa: BLE001
            raise wrap_unavailable(exc, "qdrant") from exc

    def delete_cache_query_points(self, point_ids: list[str]) -> ConnectorOutcome:
        try:
            r = httpx.post(
                f"{self._base}/collections/{self._collection}-cacheq/points/delete",
                json={"points": point_ids, "wait": True},
                timeout=_TIMEOUT,
            )
            r.raise_for_status()
            return ConnectorOutcome(ok=True, acknowledged=True, detail="deleted")
        except Exception as exc:  # noqa: BLE001
            return ConnectorOutcome(ok=False, acknowledged=False,
                                    error_code="qdrant_cache_delete_failed",
                                    detail=wrap_unavailable(exc, "qdrant").message)
