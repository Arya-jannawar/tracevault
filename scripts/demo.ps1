# TraceVault demo script (Windows PowerShell) — safe to re-run.
# Starts services, migrates, bootstraps credentials, seeds, and opens the UI.
# Destructive reset is opt-in via -Reset (local compose volumes ONLY).

param(
    [switch]$Reset = $false
)

$ErrorActionPreference = "Stop"

if ($Reset) {
    Write-Host "DESTRUCTIVE: removing tracevault compose volumes (local demo data only)" -ForegroundColor Yellow
    docker compose down -v
}

docker compose up -d postgres qdrant redis
docker compose run --rm api alembic upgrade head
docker compose run --rm api python -m app.bootstrap
docker compose up -d api worker frontend

Write-Host ""
Write-Host "TraceVault is starting:" -ForegroundColor Green
Write-Host "  UI  : http://127.0.0.1:8080"
Write-Host "  API : http://127.0.0.1:8000/docs"
Write-Host "  Credentials: printed above / backend/.local/credentials.txt"
Write-Host "Walkthrough: docs/demo-walkthrough.md"
