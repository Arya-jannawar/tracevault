# Evaluation methodology

## Setup

* **Corpus:** original deterministic synthetic enterprise-style documents
  (`backend/app/seed.py`, 12 docs) in ISOLATED evaluation workspaces
  (`eval-<run>`), never the demo workspace.
* **Gold annotations:** `data/synthetic/gold.json` — expected affected/unaffected
  artifact key prefixes, fact probes (direct, paraphrase, numerical, shared,
  control), repair expectations.
* **Held constant:** corpus, seeds, model mode, cache policy, workload,
  verification effort. Model warmup/download is excluded from operation
  latency; protocol latencies are reported from the deletion report.

## Baselines (operational definitions)

1. **vector_only** — deletes the source document's vector points only; derived
   artifacts remain. Intentionally demonstrates the weakness. Runs ONLY in
   isolated evaluation workspaces.
2. **broad_conservative** — invalidates every artifact in the bounded
   evaluation workspace after deleting the source vectors. Safe reference;
   wasteful by construction.
3. **provenance_conservative** — the production protocol (full state machine).
4. **provenance_repair** — protocol + selective summary repair.

## Metric definitions (denominators always reported; 0-denominator → N/A)

| Metric | Definition |
|---|---|
| deletion effectiveness | gold-affected artifacts invalidated or safely replaced ÷ gold-affected artifacts expected to be handled |
| residual information rate | eligible deletion-sensitive probes still retrieving deleted-only facts via supported paths ÷ eligible probes. Matches with surviving independent support are counted SEPARATELY (not leakage) |
| dependency precision | correctly predicted affected ÷ predicted affected |
| dependency recall | correctly predicted affected ÷ gold affected |
| false invalidation rate | unaffected artifacts incorrectly invalidated ÷ gold unaffected |
| information preservation | unaffected authorized artifacts still available ÷ gold unaffected |
| repair support | retained claims with surviving authorized evidence ÷ retained claims |
| deletion latency | acceptance→discovery and acceptance→completion, from the deletion report; plus measured wall time |
| overhead | connector operations, LLM calls (none in deterministic/extractive mode), regenerated artifacts; monetary cost only with explicit configured rates, otherwise "unavailable" |

`cache_hit_before_deletion` proves the cache path was warm before deletion.

## Honesty constraints

* Until a run is executed, the Evaluation Lab shows an informative empty state —
  never decorative results.
* A small synthetic experiment does NOT establish real-world privacy guarantees.
* Deterministic/demo embedding modes are labeled on every run's config.
* Attempted ≠ completed ≠ failed ≠ skipped; all four are reported per run.
