"""Embedding adapters.

* sentence-transformers  — real local MiniLM embeddings ("real mode")
* deterministic          — hashed bag-of-words vectors, stable across runs.
  ONLY for demos/tests; every response is clearly labeled via /system/capabilities
  and the mode field on answers. Never used for research measurements without
  saying so.
"""
from __future__ import annotations

import hashlib
import math
import re

from ..config import Settings
from ..errors import AdapterUnavailable

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class EmbeddingAdapter:
    name: str = "base"
    mode: str = "base"  # real | deterministic

    @property
    def dim(self) -> int:
        raise NotImplementedError

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class DeterministicEmbedding(EmbeddingAdapter):
    """Hashed bag-of-words embedding (deterministic, dependency-free)."""

    def __init__(self, dim: int = 384) -> None:
        self._dim = dim

    @property
    def name(self) -> str:
        return "deterministic-hash-embedder"

    @property
    def mode(self) -> str:
        return "deterministic"

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self._dim
            tokens = _TOKEN_RE.findall(text.lower())
            for tok in tokens:
                h = int.from_bytes(
                    hashlib.blake2b(tok.encode(), digest_size=8).digest(), "big"
                )
                idx = h % self._dim
                sign = 1.0 if (h >> 63) & 1 else -1.0
                vec[idx] += sign
                # second hash reduces collisions
                h2 = int.from_bytes(
                    hashlib.blake2b((tok + "#").encode(), digest_size=8).digest(), "big"
                )
                vec[h2 % self._dim] += 1.0 if (h2 >> 63) & 1 else -1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


class SentenceTransformerEmbedding(EmbeddingAdapter):
    """Genuine all-MiniLM-L6-v2 embeddings via sentence-transformers (lazy import)."""

    def __init__(self, model_name: str) -> None:
        try:
            from sentence_transformers import SentenceTransformer  # noqa: PLC0415
        except Exception as exc:  # noqa: BLE001
            raise AdapterUnavailable(
                "sentence-transformers is not installed in this environment. "
                "Install backend/requirements-models.txt (torch + sentence-transformers) "
                "or set EMBEDDING_PROVIDER=deterministic for the labeled demo mode."
            ) from exc
        self._model = SentenceTransformer(model_name)
        self._model_name = model_name

    @property
    def name(self) -> str:
        return self._model_name

    @property
    def mode(self) -> str:
        return "real"

    @property
    def dim(self) -> int:
        return int(self._model.get_sentence_embedding_dimension())

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(texts, normalize_embeddings=True,
                                     convert_to_numpy=True, show_progress_bar=False)
        return [v.tolist() for v in vectors]


def get_embedding_adapter(settings: Settings) -> EmbeddingAdapter:
    if settings.embedding_provider == "sentence-transformers":
        return SentenceTransformerEmbedding(settings.embedding_model)
    if settings.embedding_provider == "deterministic":
        return DeterministicEmbedding(settings.embedding_dim)
    raise AdapterUnavailable(
        f"Unknown EMBEDDING_PROVIDER '{settings.embedding_provider}' "
        "(expected 'sentence-transformers' or 'deterministic')."
    )
