# Deletion protocol & concurrency

## State machine

```
ACCEPTED ─► FENCED ─► DISCOVERING ─► INVALIDATING ─► REMOVING ─► VERIFYING ─► COMPLETED
                            │              │              │             │
                            └──────────────┴──────────────┴─────────────┴──► RETRY_PENDING
                                                                        └──► INCOMPLETE
                                                     (unrecoverable) ──► FAILED
```

Logical blocking (registry lifecycle), storage removal (connectors),
verification, and repair are tracked independently. No single green badge hides
a failed required connector.

## Acceptance (durable, linearized)

`accept_deletion` runs in ONE transaction:
1. idempotency-key check (same key + same payload → replay; same key + different
   document → `409 idempotency_conflict`);
2. `SELECT … FOR UPDATE` on the **workspace row** (serialization point with
   `gate_publish`);
3. insert `deletion_requests` (state `ACCEPTED`, `fence_epoch = gen+1`), insert
   **tombstone**, bump `workspace.fence_generation`, mark document
   `pending_deletion`, state → `FENCED`, append audit event, enqueue the
   durable `delete` job;
4. commit — **the acceptance linearization point**. From here, every read path
   observes the tombstone and every publication is fenced.

## Publication gate (TOCTOU protection)

`gate_publish(db, workspace, document_ids)`:
1. `SELECT … FOR UPDATE` on the same workspace row (orders against acceptance);
2. if any source document has a tombstone → `PublicationBlocked` (409); the
   caller cleans up staged external writes.

This is a concrete protocol, not an “if deleted” check: a query or ingestion job
that captured state before the deletion commit is rejected at commit time.
Favoring correctness over throughput, this simple locking protocol deliberately
serializes publications; no lock-free or distributed guarantees are claimed.

## Orchestrator steps (worker, retry-safe)

| Step | Does | Failure mode |
|---|---|---|
| FENCED | assert tombstone + document pending | fail fast |
| DISCOVERING | bounded affected set (direct + transitive) + coverage warnings (unknown provenance → conservative invalidation) | recorded in report |
| INVALIDATING | registry lifecycle → `invalidated` (logical block) | — |
| REMOVING | Qdrant `delete points` (full point, wait=true) · Redis keys via reverse index (no scans) · PG content purge (content redacted, lineage kept) · document title/filename redacted | any connector not ok → `RETRY_PENDING`, tombstone/fence preserved |
| VERIFYING | per-artifact checks (state, vector points gone, cache keys gone, gold similarity probes when applicable, unrelated-preservation control) | any failed/unknown → `INCOMPLETE` |
| COMPLETED | report: counts, latencies, outcomes, coverage warnings, scope exclusions | — |

Retries: exponential backoff with jitter, bounded attempts, persisted errors,
manual retry endpoint. Delete-not-found is idempotent success; unavailable
connector is `unknown` — never success. Tombstones/fences survive retries,
worker restarts and repair failures.

## Cross-store writes & reconciliation

External writes are staged: `write_intents` rows (pending) are created before
the Qdrant/Redis write and marked published after. On gate rejection the staged
writes are removed and intents cancelled. Ingestion uses deterministic chunk
IDs (`uuid5(version, index)`), so retried jobs re-upsert the same points.
Background lease recovery reclaims jobs from crashed workers. At prototype
scale, reconciliation is conservative: an unsettled intent with a stale fence
epoch is cleaned up, never exposed.

## Read-path linearization

* previously delivered responses/bytes **cannot** be retracted (documented
  boundary);
* any request that observes the committed fence (tombstone check before
  serving; registry lifecycle check before returning) must not serve affected
  content — enforced in document/chunk/summary/answer endpoints and in the
  retrieval pipeline (search hits and cache hits are re-authorized against the
  registry immediately before use; fail closed when the registry is
  unavailable);
* buffered responses only — no streaming of unvalidated content.

## Repair racing & races with source versions

Selective repair (flag-gated) publishes only after a fresh `gate_publish` over
the surviving source set; a second deletion committing in between blocks
publication (the replacement would use newly deleted evidence). Old artifacts
are never reactivated. Replacement lineage is metadata (`meta.repair_of`), not a
content dependency edge to the deleted source.
