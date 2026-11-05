#!/usr/bin/env bash
# TraceVault demo script (Linux/macOS) — safe to re-run.
# Destructive reset is opt-in via --reset (local compose volumes ONLY).
set -euo pipefail

RESET="${1:-}"
if [ "$RESET" = "--reset" ]; then
  echo "DESTRUCTIVE: removing tracevault compose volumes (local demo data only)"
  docker compose down -v
fi

docker compose up -d postgres qdrant redis
docker compose run --rm api alembic upgrade head
docker compose run --rm api python -m app.bootstrap
docker compose up -d api worker frontend

echo
echo "TraceVault is starting:"
echo "  UI  : http://127.0.0.1:8080"
echo "  API : http://127.0.0.1:8000/docs"
echo "  Credentials: printed above / backend/.local/credentials.txt"
echo "Walkthrough: docs/demo-walkthrough.md"
