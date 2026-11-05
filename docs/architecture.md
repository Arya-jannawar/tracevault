# TraceVault — Architecture

**Formal title:** Provenance-Aware Deletion and Selective Summary Repair for
Privacy-Preserving Retrieval-Augmented Generation (RAG) Systems.
**Working product name:** TraceVault — *“Know the source. Control what remains.”*
(the short brand is a design choice, not a trademark assertion).

TraceVault is a research prototype: middleware that records versioned
source→artifact dependencies in a RAG pipeline, coordinates deletion across
registered stores, verifies the outcome through supported application pathways,
and reports incomplete coverage honestly.

## Logical layers (matches synopsis §7)

```
┌─────────────────────────────────────────────────────────────────┐
│ Frontend/Application Layer  React+TS control room               │
│ documents · playground · provenance · deletions · repair ·     │
│ audit · evaluation · settings                                   │
├─────────────────────────────────────────────────────────────────┤
│ API Layer  FastAPI /api/v1 — typed contracts, session auth,     │
│ CSRF header, request IDs, content-free error envelopes          │
├─────────────────────────────────────────────────────────────────┤
│ Deletion & Verification Layer  state machine, durable queue,    │
│ fence/publication gate, verification probes, audit              │
├─────────────────────────────────────────────────────────────────┤
│ AI/RAG Layer  embeddings (MiniLM | deterministic), retrieval,   │
│ extractive/OpenAI-compatible generation, answer registration    │
├─────────────────────────────────────────────────────────────────┤
│ Provenance Layer  PostgreSQL registry (authoritative)           │
├─────────────────────────────────────────────────────────────────┤
│ Storage/Connector Layer  Qdrant (REST) · Redis · PG content     │
└─────────────────────────────────────────────────────────────────┘
```

## Data model (PostgreSQL is authoritative)

Content-bearing rows are separated from lineage metadata so content can be
purged while operation records survive:

| Table | Holds |
|---|---|
| `documents`, `document_versions` | doc metadata; **content text** per immutable version |
| `artifacts` | every registered artifact: type (`document_version/chunk/summary/answer/cache_entry`), lifecycle (`active/pending_deletion/invalidated/removed`), `provenance_status`, external `locator`, typed `meta` (chunk text/offsets, answer text/citations) |
| `dependency_edges` | `parent(source) → child(derived)` with `source_version` + relationship (`contains/has_vector/supports/summarizes/answers/cached_as`) |
| `summaries`, `claims`, `claim_supports` | summary content, claim rows, evidence links (claim ← source chunk + offsets) |
| `cache_entries` | registry mirror of every Redis answer-cache key (Redis is never authoritative) |
| `deletion_requests`, `deletion_steps`, `verification_checks` | deletion state machine + per-step attempts + probe results |
| `tombstones`, `write_intents` | durable fence markers; staged cross-store writes |
| `jobs` | PostgreSQL-backed queue with leases |
| `audit_events` | append-only, metadata-only operation records |
| `evaluation_runs` | baseline runs, measured metrics, config, counts |

**Graph convention:** `source/parent → derived/child`, always. Transitive
closure is a bounded BFS with a visited set (cycle-safe; self-edges and
cross-workspace edges are rejected at registration). Prototype scale makes a
Python BFS comfortably fast; a recursive CTE is a documented optimization.

**Vectors:** a chunk artifact owns its vector — the Qdrant point ID equals the
chunk artifact ID and the payload carries `workspace_id/document_id/
document_version_id/artifact_id/fence_epoch`. `ArtifactType.vector` exists for
future standalone vector artifacts. Full points are deleted (values + payload).

## Operating modes (all labeled, never silent)

| Mode | Embeddings | Generation | Use |
|---|---|---|---|
| real | all-MiniLM-L6-v2 (local) | OpenAI-compatible local server (Ollama/vLLM/llama.cpp, e.g. Qwen2.5-3B-Instruct) | genuine local mode |
| extractive | real or deterministic | verbatim cited excerpts, labeled `extractive` | no generative model available |
| deterministic | hashed bag-of-words | template (`deterministic`) | demos/tests ONLY, labeled |
| preview fixtures | — | — | not implemented (no fake data in measurements) |

## Deletion protocol (summary)

`ACCEPTED → FENCED → DISCOVERING → INVALIDATING → REMOVING → VERIFYING → COMPLETED`
(`RETRY_PENDING / INCOMPLETE / FAILED` with reasons). Acceptance commits the
tombstone + fence bump + job in ONE transaction — that commit is the
linearization point. Every publication passes `gate_publish` (workspace row
lock → serialized with acceptance), so a writer that captured state before the
deletion commit is rejected at commit time. Details: `docs/deletion-protocol.md`.

## Repo layout

```
frontend/   React control room (pages, components, tokens, tests)
backend/    FastAPI app, connectors, worker, migrations, tests
data/synthetic/  corpus definitions + gold.json annotations
scripts/    bootstrap / demo / smoke helpers
docs/       architecture, deletion protocol, API contract, evaluation,
            limitations, demo walkthrough
compose.yaml  postgres + qdrant + redis + api + worker + frontend (+ ollama profile)
```
