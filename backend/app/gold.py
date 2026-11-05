"""Gold annotations loader for the synthetic corpus (data/synthetic/gold.json).

Machine-readable expectations used by verification probes and the evaluation
lab. All facts are synthetic, known-public fixture content."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

GOLD_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "synthetic" / "gold.json"


@lru_cache
def load_gold() -> dict:
    with open(GOLD_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def probes_for_document_key(key: str | None) -> list[dict]:
    if not key:
        return []
    gold = load_gold()
    return [p for p in gold.get("probes", []) if p.get("target") == key]


def expected_affected(key: str) -> list[str]:
    gold = load_gold()
    return gold.get("expected_affected", {}).get(key, [])


def expected_unaffected(key: str) -> list[str]:
    gold = load_gold()
    return gold.get("expected_unaffected", {}).get(key, [])
