"""Generation adapters.

* openai-compatible — any local OpenAI-compatible server (Ollama, llama.cpp, vLLM)
* extractive       — no generative model available: answers are assembled from the
  retrieved authorized excerpts verbatim, clearly labeled `mode=extractive`.
  Never silently presented as LLM output; never invents content.
* deterministic    — test adapter for reproducible tests only.
"""
from __future__ import annotations

import httpx

from ..config import Settings
from ..errors import AdapterUnavailable

_TIMEOUT = httpx.Timeout(60.0, connect=3.0)


class LLMAdapter:
    name: str = "base"
    mode: str = "base"  # llm | extractive | deterministic

    def answer(self, question: str, excerpts: list[dict]) -> str:
        """excerpts: [{label, source, text}] — returns answer text."""
        raise NotImplementedError


class OpenAICompatibleLLM(LLMAdapter):
    def __init__(self, settings: Settings) -> None:
        self._base = settings.llm_base_url.rstrip("/")
        self._model = settings.llm_model
        self._key = settings.llm_api_key
        self.name = settings.llm_model
        self.mode = "llm"

    def answer(self, question: str, excerpts: list[dict]) -> str:
        context = "\n\n".join(
            f"[{e['label']}] (source: {e['source']})\n{e['text']}" for e in excerpts
        )
        prompt = (
            "Answer the question using ONLY the provided excerpts. Cite excerpts "
            "you use as [S1], [S2], ... If the excerpts do not contain the answer, "
            "reply exactly: INSUFFICIENT_AUTHORIZED_EVIDENCE.\n\n"
            f"Excerpts:\n{context}\n\nQuestion: {question}"
        )
        headers = {}
        if self._key:
            headers["Authorization"] = f"Bearer {self._key}"
        try:
            r = httpx.post(
                f"{self._base}/chat/completions",
                json={
                    "model": self._model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                },
                headers=headers,
                timeout=_TIMEOUT,
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as exc:  # noqa: BLE001
            raise AdapterUnavailable(
                f"LLM backend ({self._base}, model {self._model}) is unavailable: "
                f"{exc.__class__.__name__}. Start the local inference server or set "
                "LLM_PROVIDER=extractive."
            ) from exc


class ExtractiveLLM(LLMAdapter):
    """Deterministic extractive fallback: cites retrieved excerpts verbatim."""

    name = "extractive-assembler"
    mode = "extractive"

    def answer(self, question: str, excerpts: list[dict]) -> str:
        if not excerpts:
            return "INSUFFICIENT_AUTHORIZED_EVIDENCE"
        q_tokens = set(question.lower().split())
        scored = []
        for e in excerpts:
            toks = set(e["text"].lower().split())
            overlap = len(q_tokens & toks) / (len(q_tokens) or 1)
            scored.append((overlap, e))
        scored.sort(key=lambda pair: -pair[0])
        top = [e for _, e in scored[:3]]
        lines = [f"[{e['label']}] {e['text']}" for e in top]
        return "Based on the retrieved authorized excerpts (extractive mode, no generative model configured):\n" + "\n".join(lines)


class DeterministicLLM(LLMAdapter):
    """Test adapter: echoes the first excerpt. Identified as `deterministic`."""

    name = "deterministic-test-llm"
    mode = "deterministic"

    def answer(self, question: str, excerpts: list[dict]) -> str:
        if not excerpts:
            return "INSUFFICIENT_AUTHORIZED_EVIDENCE"
        first = excerpts[0]
        return f"Deterministic answer based on [{first['label']}]: {first['text']}"


def get_llm_adapter(settings: Settings) -> LLMAdapter:
    if settings.llm_provider == "openai-compatible":
        return OpenAICompatibleLLM(settings)
    if settings.llm_provider == "extractive":
        return ExtractiveLLM()
    if settings.llm_provider == "deterministic":
        return DeterministicLLM()
    raise AdapterUnavailable(
        f"Unknown LLM_PROVIDER '{settings.llm_provider}' "
        "(expected 'openai-compatible', 'extractive' or 'deterministic')."
    )
