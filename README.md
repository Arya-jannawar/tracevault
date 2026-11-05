# TraceVault

**Provenance-Aware Deletion and Selective Summary Repair for Privacy-Preserving
Retrieval-Augmented Generation (RAG) Systems**

*Know the source. Control what remains.* — a research prototype (academic
project, Vishwakarma Institute of Technology, FF No. 180). TraceVault is
middleware that records versioned source→artifact dependencies in a RAG
pipeline, coordinates deletion across registered stores, verifies the outcome
through supported application pathways, and reports incomplete coverage
honestly. It controls **stored RAG artifacts**, not model weights, and claims
no legal compliance, model unlearning, or forensic erasure.

![status](https://img.shields.io/badge/status-research_prototype-orange)

## What works (measured in this repo)

- Ingestion → chunking → embeddings → vectors → registered summaries with
  claim-level evidence links (idempotent, durable queue)
- Cited RAG answers with exact-query answer cache (registry-validated hits)
- Fenced deletion protocol: `ACCEPTED → FENCED → DISCOVERING → INVALIDATING →
  REMOVING → VERIFYING → COMPLETED`, with honest `RETRY_PENDING / INCOMPLETE`
  outcomes; per-connector acknowledgements; content purge with surviving
  lineage; delayed reappearance checks
- Selective summary repair (flag-gated, strict mode): keeps only claims with
  surviving authorized support; zero surviving sources ⇒ evidence-insufficient,
  never invented content
- Evaluation lab: 4 baselines (`vector_only`, `broad_conservative`,
  `provenance_conservative`, `provenance_repair`) over a synthetic corpus with
  gold annotations and measured metrics
- Research control-room frontend: overview, documents, playground, provenance
  explorer, deletion center, repair lab, audit, evaluation, settings

## Architecture

See [docs/architecture.md](docs/architecture.md) · deletion protocol:
[docs/deletion-protocol.md](docs/deletion-protocol.md) · API contract:
[docs/api-contract.md](docs/api-contract.md) · evaluation methodology:
[docs/evaluation.md](docs/evaluation.md) · scope & limitations:
[docs/limitations.md](docs/limitations.md) · 5-minute demo:
[docs/demo-walkthrough.md](docs/demo-walkthrough.md)

## Prerequisites

- Docker Desktop (with Compose v2+) — **start it first**
- Python 3.12+ (developed on 3.14) with `python -m venv` support
- Node 20+ (frontend build)

No GPU, no paid API, no model download required for the labeled demo mode.

## Quick start (Docker Compose — recommended)

PowerShell (Windows):

```powershell
cd D:\VIT\EDI PROJECT\tracevault
copy .env.example .env
# REQUIRED: put a session secret into .env
python -c "import secrets; print('SESSION_SECRET=' + secrets.token_urlsafe(48))"
#   paste the printed line into .env (replace SESSION_SECRET=)

docker compose up -d postgres qdrant redis
docker compose run --rm api alembic upgrade head
docker compose run --rm api python -m app.bootstrap   # prints generated operator credentials
docker compose up -d api worker frontend
```

Linux/macOS: identical except `cp .env.example .env`.

- Frontend: http://127.0.0.1:8080 · API docs: http://127.0.0.1:8000/docs
- Credentials: printed once by `app.bootstrap` and written to
  `backend/.local/credentials.txt` (gitignored). No fixed production passwords.
- Seeding is idempotent (`SEED_ON_START=true`): 12 synthetic documents ingest
  via the worker; safe to re-run.

### Optional: real embeddings + local LLM (real mode)

```powershell
# embeddings: build with the model stack (~200MB + ~90MB model download)
docker compose build --build-arg INSTALL_MODELS=true api worker
# then in .env:  EMBEDDING_PROVIDER=sentence-transformers

# LLM via Ollama (profile):
docker compose --profile llm up -d ollama
docker compose exec ollama ollama pull qwen2.5:3b-instruct
# then in .env:  LLM_PROVIDER=openai-compatible
#                LLM_BASE_URL=http://127.0.0.1:11434/v1
docker compose up -d api worker
```

`EMBEDDING_PROVIDER=deterministic` + `LLM_PROVIDER=extractive` (the defaults)
run with zero downloads and are clearly labeled in the UI and API — they are
demo modes, not research-grade results.

## Local development (without Docker for the app itself)

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r backend\requirements.txt
# services (compose) can still run in Docker:
docker compose up -d postgres qdrant redis

cd backend
copy ..\.env .env            # adjust DATABASE_URL host if needed
..\.venv\Scripts\alembic upgrade head
..\.venv\Scripts\python -m app.bootstrap
..\.venv\Scripts\uvicorn app.main:app --port 8000 --reload   # API
..\.venv\Scripts\python -m app.worker                        # worker (2nd terminal)

cd ..\frontend
npm install
npm run dev                   # http://127.0.0.1:5173 (proxies /api → :8000)
```

## Tests

```powershell
cd backend
..\.venv\Scripts\python -m pytest             # unit tests (SQLite + labeled test adapters)
docker compose up -d postgres qdrant redis    # then:
..\.venv\Scripts\python -m pytest -m integration   # REAL PostgreSQL/Qdrant/Redis

cd ..\frontend
npm ci ; npx tsc --noEmit ; npm run build ; npx vitest run
```

A skipped integration test is **not** a pass — run them with services up.

## Demo (5 minutes)

Follow [docs/demo-walkthrough.md](docs/demo-walkthrough.md): cached answer →
provenance graph → deletion-impact preview → fenced deletion → blocked
retrieval (`410 content_blocked`) → independent-support survival → repair →
outage ⇒ honest INCOMPLETE → evaluation run.

## Operating-mode honesty

Every answer carries `mode` (`llm` / `extractive` / `deterministic`) and the
UI labels it. `GET /api/v1/system/capabilities` publishes the full declared
boundary. Deletion states distinguish **blocked** vs **removed** vs
**verified** vs **coverage incomplete** — the UI makes INCOMPLETE visually
distinct from COMPLETED.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `docker compose` can't connect | start Docker Desktop, wait for the whale icon |
| `docker pull` fails with `registry-1.docker.io` timeouts | Docker Hub is blocked on some networks — use `public.ecr.aws/docker/library/<image>:<tag>` (official mirror) and `docker tag` it to the compose name, e.g. `docker pull public.ecr.aws/docker/library/redis:7.4.1 && docker tag public.ecr.aws/docker/library/redis:7.4.1 redis:7.4.1` |
| API 503 `adapter_unavailable` (embeddings) | install `requirements-models.txt` or set `EMBEDDING_PROVIDER=deterministic` |
| API 503 `adapter_unavailable` (LLM) | start Ollama/llama.cpp or set `LLM_PROVIDER=extractive` |
| Login rejected | re-run `python -m app.bootstrap` (or set `ADMIN_PASSWORD` in .env) |
| Documents stuck "ingesting" | worker not running: `docker compose up -d worker` |
| `415 unsupported_content` on PDF | scanned/image-only PDF — OCR not implemented; use text PDFs |
| Reset demo data (**destructive, local volumes only**) | `docker compose down -v` then start again |

### Network-restricted setup (hybrid, used for the verified live demo)

If in-container builds stall on your network, run the backing services in
Docker and the app from a local venv — this is exactly how the delivered demo
was verified:

```powershell
docker compose up -d postgres qdrant redis
cd backend ; ..\.venv\Scripts\alembic upgrade head ; ..\.venv\Scripts\python -m app.bootstrap
start ..\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000   # API
start ..\.venv\Scripts\python -m app.worker                                          # worker
docker run -d --name tracevault-frontend-dev -p 127.0.0.1:8080:80 `
  -v "$(pwd)\frontend\nginx.dev.conf:/etc/nginx/conf.d/default.conf:ro" `
  tracevault-frontend:latest   # build once: docker compose build frontend
```

## Repository layout

```
frontend/  React control room (src/pages, src/components, tokens, tests)
backend/   FastAPI app (app/), migrations/, tests/
data/synthetic/   gold.json annotations (corpus in backend/app/seed.py)
scripts/   demo + smoke helpers
docs/      architecture, deletion protocol, API contract, evaluation,
           limitations, demo walkthrough
```

## License / attribution

Academic prototype by Group (SEDA) 15, CSE(AI), SY — VIT Pune. Original
synthetic corpus; no real personal data is included anywhere in fixtures.
