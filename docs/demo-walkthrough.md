# 5-minute demo walkthrough (proves the core behavior)

All commands are PowerShell-friendly; notes for Linux/macOS where they differ.
The demo uses ONLY the seeded synthetic corpus (no personal data).

## 0. Start (first time)

```powershell
cd D:\VIT\EDI PROJECT\tracevault
copy .env.example .env
# generate a session secret and put it in .env:
python -c "import secrets; print('SESSION_SECRET=' + secrets.token_urlsafe(48))"

docker compose up -d postgres qdrant redis      # services
docker compose run --rm api alembic upgrade head
docker compose run --rm api python -m app.bootstrap   # prints generated operator password
docker compose up -d api worker frontend
```

Open http://127.0.0.1:8080 (or the API at http://127.0.0.1:8000/docs).
Sign in as `admin` + the generated password (also in `backend/.local/credentials.txt`).
The synthetic corpus seeds automatically (12 documents ingest via the worker).

## 1. Cited answer + real cache hit (Playground)

1. Playground → ask: **“When is the Nightingale phase 2 rollout scheduled?”**
2. Observe: cited answer (extractive/LLM mode label), latency, citations.
3. Ask again → **cache hit (exact)** badge, near-zero latency.

## 2. Provenance (Explorer)

Open Provenance → root `document:` of Project Nightingale Phase 2 Brief →
see version → chunks → summaries → answers → cache entries, including the
multi-source summary `summaryAB` (claim 1 ← docA, claim 2 ← docB).

## 3. Deletion impact preview + fenced deletion

1. Documents → Nightingale brief → **Deletion impact**: affected counts
   (chunks, summaries, answers, cache entries) + coverage notes.
2. **Delete document** → confirm (names the document + counts).
3. Deletion Center → job runs the state machine: FENCED → DISCOVERING →
   INVALIDATING → REMOVING → VERIFYING → **COMPLETED** (per-connector
   outcomes visible; scope exclusions always listed).

## 4. Verify the block (Playground + Documents)

1. Re-ask the Nightingale question → **INSUFFICIENT_AUTHORIZED_EVIDENCE**
   (no cached answer, no vectors).
2. Documents → the deleted document shows tombstoned/redacted state;
   content endpoint returns **410 content_blocked**.
3. Ask “Where must the quarterly security compliance training be completed?”
   → still answered from **docB** (independent support survives).

## 5. Selective repair (Repair Lab — flag on)

1. `.env`: `ENABLE_SELECTIVE_REPAIR=true` → restart api+worker.
2. Deletion request detail → Repair candidates: `summaryAB` shows
   `surviving_supports > 0` (docB). Repair → new summary version published
   containing ONLY the independently supported LMS claim — the Nightingale
   fact is gone; the docB claim remains.

## 6. Outage → honest INCOMPLETE (optional)

`docker compose stop qdrant` → delete another document → Deletion Center shows
`RETRY_PENDING/INCOMPLETE` (never green). `start qdrant` → **Retry** → completes.

## 7. Evaluation lab

Evaluation → scenario `single_document_deletion_docA`, baseline
`provenance_conservative`, seed 42 → Launch → measured metrics appear with
denominators; compare `vector_only` (weak) vs `provenance_conservative` (safe)
vs `provenance_repair` (safe + preserved information).
