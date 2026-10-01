param(
    [string]$Action = "urls"
)

# Resolves a setting the way docker compose does: a real environment variable
# wins, then the value in .env, then the compose default.
function Get-EnvSetting {
    param([string]$Name, [string]$Default)

    $fromEnv = [Environment]::GetEnvironmentVariable($Name)
    if ($fromEnv) { return $fromEnv }

    $envFile = Join-Path $PSScriptRoot ".env"
    if (Test-Path $envFile) {
        $line = Get-Content $envFile |
            Where-Object { $_ -match "^\s*$([regex]::Escape($Name))\s*=" } |
            Select-Object -Last 1
        if ($line) {
            $value = ($line -split "=", 2)[1].Trim().Trim('"').Trim("'")
            if ($value) { return $value }
        }
    }
    return $Default
}

switch ($Action.ToLower()) {
    "urls" {
        $pgadmin = "$(Get-EnvSetting 'PGADMIN_DEFAULT_EMAIL' 'admin@admin.com') / $(Get-EnvSetting 'PGADMIN_DEFAULT_PASSWORD' 'admin')"
        $grafana = "$(Get-EnvSetting 'GRAFANA_ADMIN_USER' 'admin') / $(Get-EnvSetting 'GRAFANA_ADMIN_PASSWORD' 'admin')"
        $s3ui = "$(Get-EnvSetting 'S3_BROWSER_USER' 'admin') / $(Get-EnvSetting 'S3_BROWSER_PASS' 'admin')"

        Write-Host "`n=== FastAPI Dockerized Platform Services ===" -ForegroundColor Cyan
        Write-Host "Developer Portal:   http://localhost" -ForegroundColor Green
        Write-Host "FastAPI Swagger:    http://localhost:8000/docs"
        Write-Host "pgAdmin 4:          http://localhost:5050  ($pgadmin)"
        Write-Host "Redis Commander:    http://localhost:8081"
        Write-Host "Mailpit Inbox:      http://localhost:8025"
        Write-Host "Grafana:            http://localhost:3000  ($grafana)"
        Write-Host "Prometheus:         http://localhost:9090"
        Write-Host "Locust Swarm:       http://localhost:8089"
        Write-Host "LocalStack S3:      http://localhost:4566"
        Write-Host "S3 Web UI (Sairo):  http://localhost:8085  ($s3ui)`n"
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

        # Same Postgres settings the db container was created with; user and
        # password are URL-encoded so characters like @ or % survive in the DSN.
        $pgUser = [System.Uri]::EscapeDataString((Get-EnvSetting 'POSTGRES_USER' 'postgres'))
        $pgPassword = [System.Uri]::EscapeDataString((Get-EnvSetting 'POSTGRES_PASSWORD' 'postgrespassword'))
        $pgDb = Get-EnvSetting 'POSTGRES_DB' 'appdb'
        $pgPort = Get-EnvSetting 'POSTGRES_PORT' '5432'

        $env:DATABASE_URL = "postgresql://${pgUser}:${pgPassword}@localhost:${pgPort}/${pgDb}"
        $env:REDIS_URL = "redis://localhost:6379/0"
        $env:MAILPIT_HOST = "localhost"
        $env:AWS_ENDPOINT_URL = "http://localhost:4566"
        uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
    }
    default {
        Write-Host "Usage: .\dev.ps1 [urls | run | test | migrate | status]" -ForegroundColor Yellow
    }
}
