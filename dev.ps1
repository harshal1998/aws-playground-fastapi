param(
    [string]$Action = "urls"
)

switch ($Action.ToLower()) {
    "urls" {
        Write-Host "`n=== FastAPI Dockerized Platform Services ===" -ForegroundColor Cyan
        Write-Host "Developer Portal:   http://localhost" -ForegroundColor Green
        Write-Host "FastAPI Swagger:    http://localhost:8000/docs"
        Write-Host "pgAdmin 4:          http://localhost:5050  (admin@admin.com / admin)"
        Write-Host "Redis Commander:    http://localhost:8081"
        Write-Host "Mailpit Inbox:      http://localhost:8025"
        Write-Host "Grafana:            http://localhost:3000  (admin / admin)"
        Write-Host "Prometheus:         http://localhost:9090"
        Write-Host "Locust Swarm:       http://localhost:8089"
        Write-Host "LocalStack S3:      http://localhost:4566"
        Write-Host "S3 Web UI (Sairo):  http://localhost:8085  (admin / admin)`n"
    }
    "test" {
        docker compose run --rm test
    }
    "migrate" {
        docker compose run --rm migration
    }
    "status" {
        docker compose ps
    }
    "run" {
        # Stop containerized API if running so port 8000 is free
        docker compose stop api 2>$null
        Write-Host "Starting FastAPI locally on host with hot-reload..." -ForegroundColor Green
        $env:DATABASE_URL = "postgresql://postgres:postgrespassword@localhost:5432/appdb"
        $env:REDIS_URL = "redis://localhost:6379/0"
        $env:MAILPIT_HOST = "localhost"
        $env:AWS_ENDPOINT_URL = "http://localhost:4566"
        uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
    }
    default {
        Write-Host "Usage: .\dev.ps1 [urls | run | test | migrate | status]" -ForegroundColor Yellow
    }
}
