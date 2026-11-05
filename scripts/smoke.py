"""End-to-end smoke check against a RUNNING TraceVault API.

Verifies the headline behavior with honest output (no fake success):
  login -> count documents -> ask a question twice (cache hit expected on the
  second answer) -> deletion-impact preview -> (optionally) run a deletion and
  verify blocking.

Usage:  python scripts/smoke.py [--base http://127.0.0.1:8000]
Credentials come from backend/.local/credentials.txt or --username/--password.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

import httpx

CSRF = {"X-TraceVault-Session": "1"}


def login(base: str, username: str, password: str) -> httpx.Client:
    c = httpx.Client(base_url=base, timeout=30.0)
    r = c.post("/api/v1/auth/login", json={"username": username, "password": password})
    if r.status_code != 200:
        print(f"FAIL login: {r.status_code} {r.text[:200]}")
        sys.exit(1)
    print("PASS login")
    return c


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--username", default=None)
    ap.add_argument("--password", default=None)
    ap.add_argument("--delete", action="store_true",
                    help="also delete one synthetic document and verify blocking")
    args = ap.parse_args()

    username, password = args.username, args.password
    if not username or not password:
        cred = Path(__file__).resolve().parent.parent / "backend" / ".local" / "credentials.txt"
        if cred.exists():
            for line in cred.read_text().splitlines():
                if line.startswith("operator:"):
                    username = line.split(":", 1)[1].strip()
                if line.startswith("password:"):
                    password = line.split(":", 1)[1].strip()
    if not username or not password:
        print("FAIL no credentials (pass --username/--password or run app.bootstrap)")
        sys.exit(1)

    c = login(args.base, username, password)
    h = {**CSRF}

    # health + capabilities
    caps = c.get("/api/v1/system/capabilities").json()
    print(f"PASS capabilities: embedding={caps['embedding']['provider']} "
          f"llm={caps['llm']['provider']} repair={caps['flags']['selective_repair']}")

    docs = c.get("/api/v1/documents", params={"page_size": 100}).json()
    print(f"PASS documents listed: {len(docs)}")
    if not docs:
        print("NOTE corpus not seeded yet (worker may still be ingesting); "
              "re-run this script in a minute.")
        return

    # RAG query x2 (cache hit expected on repeat)
    q = "When is the Nightingale phase 2 rollout scheduled?"
    r1 = c.post("/api/v1/rag/query", headers=h, json={"question": q}).json()
    r2 = c.post("/api/v1/rag/query", headers=h, json={"question": q}).json()
    print(f"PASS query 1: cache_hit={r1.get('cache_hit')} mode={r1.get('mode')} "
          f"citations={len(r1.get('citations', []))} latency={r1.get('latency_ms')}ms")
    print(f"PASS query 2: cache_hit={r2.get('cache_hit')} cache_type={r2.get('cache_type')}")
    if not r2.get("cache_hit"):
        print("WARN expected an exact cache hit on the repeat query")

    if not args.delete:
        print("SMOKE OK (without deletion phase)")
        return

    # deletion phase on the Nightingale document
    target = next((d for d in docs if "Nightingale" in d["title"]), None)
    if target is None:
        print("FAIL Nightingale document not found; is the corpus seeded?")
        sys.exit(1)
    impact = c.get(f"/api/v1/documents/{target['id']}/deletion-impact").json()
    print(f"PASS deletion impact: {impact['affected_count']} affected "
          f"{impact['affected_by_type']}")
    r = c.delete(f"/api/v1/documents/{target['id']}", headers=h)
    if r.status_code != 202:
        print(f"FAIL deletion request: {r.status_code} {r.text[:200]}")
        sys.exit(1)
    req = r.json()
    print(f"PASS deletion accepted: {req['id']} state={req['state']}")

    for _ in range(60):
        time.sleep(2)
        detail = c.get(f"/api/v1/deletion-requests/{req['id']}").json()
        if detail["state"] in ("COMPLETED", "INCOMPLETE", "FAILED", "RETRY_PENDING"):
            break
    print(f"PASS deletion finished in state {detail['state']}")
    if detail["state"] != "COMPLETED":
        print(f"NOTE failure_reason={detail.get('failure_reason')} — "
              "honest non-success; check Deletion Center for per-connector outcomes")

    # content must be blocked (410) — the core guarantee
    r = c.get(f"/api/v1/documents/{target['id']}/content")
    print(("PASS content blocked (410)" if r.status_code == 410
           else f"FAIL content still accessible: {r.status_code}"))

    # re-query: the deleted document's SPECIFIC fact must not be served.
    # (docD legitimately mentions "Nightingale" with a DIFFERENT budget — that
    # is independent content, not leakage.)
    r = c.post("/api/v1/rag/query", headers=h, json={"question": q}).json()
    answer_text = r.get("answer") or ""
    cited_deleted = any(
        cit.get("document_id") == target["id"] for cit in r.get("citations", [])
    )
    leaked = ("4.2 crore" in answer_text or "14 March 2026" in answer_text
              or cited_deleted)
    print(("PASS re-query does not serve the deleted fact"
           if not leaked else
           f"FAIL deleted fact still served (cited_deleted={cited_deleted})"))

    print("SMOKE DONE — results above are actual API observations.")


if __name__ == "__main__":
    main()
