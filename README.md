# 🚀 AWS Playground FastAPI

A scalable, production-ready local development platform built with **FastAPI**, **PostgreSQL**, **Redis**, **LocalStack (AWS S3)**, **Mailpit**, and an observability suite with **Prometheus**, **Grafana**, **Locust**, and **Nginx**.

---

## 📋 Table of Contents

- [Overview & Architecture](#-overview--architecture)
- [Service Catalog & Ports](#-service-catalog--ports)
- [Project Structure](#-project-structure)
- [Prerequisites](#-prerequisites)
- [Quick Start](#-quick-start)
- [Available Endpoints & Features](#-available-endpoints--features)
  - [Cache-Aside Pattern (Redis)](#cache-aside-pattern-redis)
  - [Background Email Notifications (Mailpit)](#background-email-notifications-mailpit)
  - [Simulated Cloud Storage (LocalStack S3)](#simulated-cloud-storage-localstack-s3)
  - [Observability & Metrics (Prometheus & Grafana)](#observability--metrics-prometheus--grafana)
- [Load & Performance Testing](#-load--performance-testing)
  - [Locust Web UI](#1-locust-distributed-load-testing)
  - [Standalone Benchmark Script](#2-standalone-concurrency-benchmark)
- [Database Migrations (Alembic)](#-database-migrations-alembic)
- [Automated Testing (Pytest)](#-automated-testing-pytest)
- [CI/CD (GitHub Actions)](#-cicd-github-actions)
- [Developer CLI Helper (PowerShell)](#-developer-cli-helper-powershell)

---

## 🏛 Overview & Architecture

This repository provides an all-in-one local environment orchestrated with Docker Compose:

* **FastAPI Application (`api`)**: High-performance asynchronous API using `asyncpg` and `redis.asyncio`.
* **Nginx Reverse Proxy (`nginx`)**: Unified gateway routing traffic and serving a custom Developer Portal.
* **PostgreSQL (`db`)**: Relational database with automatic healthchecks and connection pooling.
* **Redis (`redis`)**: In-memory cache implementing the Cache-Aside pattern.
* **LocalStack (`localstack`)**: Local AWS cloud emulator running mock S3 object storage.
* **Mailpit (`mailpit`)**: Mock SMTP server with a web UI for testing email notifications without sending real emails.
* **Prometheus & Grafana (`prometheus`, `grafana`)**: Automated metrics collection and dashboard visualization.
* **Locust (`locust`)**: Distributed load generator for stress-testing API endpoints.
* **pgAdmin 4 & Redis Commander**: Web GUIs for database inspection and cache monitoring.

---

## 🌐 Service Catalog & Ports

When the stack is running, all services are accessible locally:

| Service | Port / URL | Credentials / Notes |
| :--- | :--- | :--- |
| **Developer Portal** | [http://localhost](http://localhost) | Interactive web portal for all tools |
| **FastAPI Swagger Docs** | [http://localhost:8000/docs](http://localhost:8000/docs) | OpenAPI interactive documentation |
| **Nginx API Gateway** | [http://localhost/api/](http://localhost/api/) | Proxied through Nginx (`/docs`, `/api/items`) |
| **Grafana Dashboard** | [http://localhost:3000](http://localhost:3000) | `admin` / `admin` (Prometheus datasource preloaded) |
| **Prometheus Metrics** | [http://localhost:9090](http://localhost:9090) | Auto-scrapes `api:8000/metrics` every 5s |
| **Locust Swarm UI** | [http://localhost:8089](http://localhost:8089) | Performance & load testing interface |
| **Mailpit Web Inbox** | [http://localhost:8025](http://localhost:8025) | SMTP listening on port `1025` |
| **pgAdmin 4** | [http://localhost:5050](http://localhost:5050) | `admin@admin.com` / `admin` (DB preconfigured) |
| **Redis Commander** | [http://localhost:8081](http://localhost:8081) | Web GUI to view cached keys and TTLs |
| **LocalStack S3** | [http://localhost:4566](http://localhost:4566) | S3 endpoint mock (Bucket: `fastapi-bucket`) |
| **S3 Browser UI** | [http://localhost:8085](http://localhost:8085) | `admin` / `admin` (Dedicated S3 web client) |


---

## 📁 Project Structure

All Docker and service configs are organized in `docker/`, leaving the core Python application cleanly structured in `app/`:

```text
aws-playground-fastapi/
├── app/                                 # 🐍 Core FastAPI Application
│   ├── main.py                          # Application entrypoint & lifespan context
│   ├── core/                            # Foundational configuration, DB pools, Redis, metrics
│   │   ├── config.py                    # Environment settings
│   │   ├── database.py                  # PostgreSQL connection pool (asyncpg)
│   │   ├── redis.py                     # Redis async client & pool
│   │   └── metrics.py                   # Prometheus latency middleware & counter
│   ├── schemas/                         # Pydantic request & response models
│   │   └── item.py                      # Item validation schemas
│   ├── services/                        # Business logic & integrations
│   │   ├── items.py                     # Item queries & Cache-Aside logic
│   │   ├── email.py                     # Mailpit background SMTP dispatch
│   │   ├── s3.py                        # Class-based S3Service (buckets & object storage)
│   │   └── aws.py                       # Unified class-based AWSService (SQS, DynamoDB, SecretsManager)
│   ├── api/                             # API routing layer
│   │   ├── deps.py                      # FastAPI dependency injection
│   │   └── v1/
│   │       ├── router.py                # Combined v1 APIRouter
│   │       └── endpoints/               # Route controllers
│   │           ├── root.py              # Health check (/)
│   │           ├── items.py             # Item CRUD (/items)
│   │           ├── s3.py                # LocalStack S3 operations (/s3)
│   │           └── aws.py               # LocalStack AWS operations (/aws)
│   ├── tests/                           # 🧪 Colocated Automated Test Suite
│   │   ├── __init__.py
│   │   └── test_api.py                  # Pytest API integration tests
│   └── alembic/                         # 🗄️ Colocated Database Migrations
│       ├── versions/
│       │   └── 001_create_items_table.py
│       └── env.py
│
├── docker/                              # 📦 Docker & Service Configurations
│   ├── Dockerfile                       # FastAPI multi-stage container
│   ├── nginx/                           # Reverse proxy configuration
│   ├── portal/                          # Developer portal web UI
│   ├── prometheus/                      # Prometheus scrape targets
│   ├── grafana/                         # Provisioned datasources & dashboards
│   ├── pgadmin/                         # Preconfigured database connection
│   └── locust/                          # Load testing scenario (locustfile.py)
│
├── scripts/                             # 🛠️ Utility Scripts
│   └── load_test.py                     # High-concurrency multithreaded RPS tester
│
├── compose.yml                          # 🐳 Complete 11-service Docker Compose stack
├── dev.ps1                              # ⚡ PowerShell management helper
├── alembic.ini                          # Migration CLI config (points to app/alembic)
├── requirements.txt                     # Pinned Python package dependencies
└── .env.example                         # Environment variable definitions
```

---

## ⚙️ Prerequisites

* [Docker Desktop](https://www.docker.com/products/docker-desktop/) with Docker Compose v2+ installed and running.
* *(Optional)* Python 3.11+ if running tests or benchmarks outside Docker.

---

## ⚡ Quick Start

### 1. Configure Environment Variables
Copy the example environment configuration:

```bash
# Windows PowerShell
cp .env.example .env

# Linux / macOS
cp .env.example .env
```

### 2. Launch the Stack
Start all containers in detached mode:

```bash
docker compose up -d --build
```

### 3. Verify Container Status
Check that all 11 services are running and healthy:

```bash
docker compose ps
```

### 4. Open Developer Portal
Navigate to:
👉 **[http://localhost](http://localhost)** to explore all services from a unified dashboard.

### 5. Running FastAPI Directly on Host (Local Dev & Hot-Reload)
If you want to run the FastAPI app directly on your host machine (outside Docker) for local debugging, IDE breakpoints, or rapid code iteration:

1. **Keep backing services running in Docker**:
   ```bash
   docker compose up -d db redis mailpit localstack
   ```
2. **Launch with the PowerShell helper**:
   ```powershell
   .\dev.ps1 run
   ```
   *(This automatically stops the containerized `api` to free port 8000, routes connections to `localhost`, and starts Uvicorn with hot-reload)*

   **Or run manually**:
   ```powershell
   # Ensure containerized API is stopped so port 8000 is free
   docker compose stop api

   # Run with Uvicorn
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

---

## 🎯 Available Endpoints & Features

### Core API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Health check and container hostname/ID. |
| `POST` | `/items` | Inserts a new item, clears cache, and triggers mock email. |
| `GET` | `/items?limit=10` | Fetches items (Cached in Redis for 60s). |
| `GET` | `/items/{id}` | Fetches a single item by ID (Cached in Redis). |
| `POST` | `/s3/upload-sample` | Uploads a test document to LocalStack S3 bucket. |
| `GET` | `/s3/objects` | Lists all documents stored in LocalStack S3. |
| `GET` | `/aws/status` | Returns LocalStack connection health and active AWS services. |
| `GET` | `/aws/sqs/queues` | Lists SQS queues and message counts. |
| `POST` | `/aws/sqs/messages` | Enqueues a message payload to an SQS queue. |
| `GET` | `/aws/dynamodb/tables` | Lists DynamoDB tables and status. |
| `GET` | `/aws/dynamodb/items` | Scans items from a DynamoDB table. |
| `GET` | `/aws/secrets` | Lists secrets from Secrets Manager. |
| `GET` | `/metrics` | Exposes Prometheus metrics (`http_requests_total`, latency). |


### Cache-Aside Pattern (Redis)
* When calling `GET /items`:
  * If the key `items:limit:{limit}` exists in Redis, data is served from **cache** (`"source": "cache (Redis)"`).
  * If not, it is fetched from **PostgreSQL**, saved to Redis with a 60-second TTL, and returned (`"source": "database (PostgreSQL)"`).
* When calling `POST /items`:
  * The new item is saved to PostgreSQL.
  * All `items:*` keys in Redis are automatically **invalidated** to prevent stale reads.

### Background Email Notifications (Mailpit)
When creating an item (`POST /items`), FastAPI schedules a non-blocking `BackgroundTask` to deliver an SMTP notification to Mailpit.
* View delivered emails at: **[http://localhost:8025](http://localhost:8025)**

### Simulated Cloud Storage & AWS Services (LocalStack)
All AWS services are 100% offline and run locally in Docker on port `4566`:
1. **Option 1: In-Portal Multi-Service AWS Explorer**:
   * Open **[http://localhost](http://localhost)** and switch to the **AWS Services** tab to manage S3 buckets, SQS queues, DynamoDB tables, and Secrets Manager.
2. **Option 2: Dedicated S3 Web Browser Container (Sairo)**:
   * Open **[http://localhost:8085](http://localhost:8085)** (Login: `admin` / `admin`) for full bucket management, prefix trees, search, and direct file downloads.


* **Via API / Curl**:
  ```bash
  # Upload sample document
  curl -X POST "http://localhost:8000/s3/upload-sample?filename=report.txt"

  # List all objects in bucket
  curl "http://localhost:8000/s3/objects"

  # View / download file content
  curl "http://localhost:8000/s3/file?key=report.txt"
  ```


### Observability & Metrics (Prometheus & Grafana)
* All HTTP requests are intercepted by custom latency middleware.
* Prometheus scrapes `/metrics` automatically every 5 seconds.
* Check Prometheus graphs: **[http://localhost:9090](http://localhost:9090)**
* Open Grafana: **[http://localhost:3000](http://localhost:3000)** (Login: `admin` / `admin`).

---

## 🚀 Load & Performance Testing

### 1. Locust (Distributed Load Testing)
Locust runs as a pre-configured service in Docker Compose.
1. Open **[http://localhost:8089](http://localhost:8089)** in your browser.
2. Enter the desired number of users (e.g., `100`) and spawn rate (e.g., `10`).
3. Host is pre-configured to `http://api:8000`. Click **Start Swarming**.
4. Observe real-time response times, failure rates, and RPS charts.

### 2. Standalone Concurrency Benchmark
You can run the multithreaded benchmark script locally using `uv` or Python:

```bash
# Run with 1,000 concurrent threads sending 10,000 requests
python scripts/load_test.py
```
Or override parameters via environment variables:
```bash
BENCHMARK_URL="http://localhost:8000/items?limit=5" TOTAL_REQUESTS=5000 CONCURRENCY=500 python scripts/load_test.py
```

---

## 🗄 Database Migrations (Alembic)

Database migrations run inside Docker without needing local PostgreSQL tools installed:

```bash
# Run migrations using Docker Compose
docker compose run --rm migration

# Or using the PowerShell helper
.\dev.ps1 migrate
```

To create a new migration:
```bash
docker compose run --rm api alembic revision -m "add_new_column"
```

---

## 🧪 Automated Testing (Pytest)

Run the automated integration test suite against the live Docker stack:

```bash
# Run test suite inside Docker
docker compose run --rm test

# Or using the PowerShell helper
.\dev.ps1 test
```

---

## 🔁 CI/CD (GitHub Actions)

Two workflows in `.github/workflows/` automate quality checks and image publishing:

- **`ci.yml`** — runs on every PR into `develop` (and on push to `develop`):
  - `lint`: `ruff check .` (config in `pyproject.toml`)
  - `integration-test`: builds the API image, brings up `db`/`redis`/`localstack`/`mailpit`/`api` via Docker Compose, runs Alembic migrations, then the `app/tests/` pytest suite against the live stack
- **`cd.yml`** — runs after `ci.yml` succeeds on `develop`: builds the `docker/Dockerfile` image and pushes it to GitHub Container Registry as `ghcr.io/<owner>/<repo>:latest` and `:<commit-sha>`

`develop` is a protected branch (PRs required, no force-push/deletion), so both workflows exist to give an incoming PR a pass/fail signal before merge.

To run the same lint check locally:

```bash
pip install -r requirements-dev.txt
ruff check .
```

---

## ⚡ Developer CLI Helper (PowerShell)

On Windows, use [dev.ps1](dev.ps1) for quick shortcuts:

```powershell
# Print all service links and credentials
.\dev.ps1 urls

# Run integration tests
.\dev.ps1 test

# Run database migrations
.\dev.ps1 migrate

# Run FastAPI directly on host with auto-reload (stops docker api container)
.\dev.ps1 run

# Check status of all containers
.\dev.ps1 status
```

---

## 🛑 Stopping & Teardown

```bash
# Stop all containers (keeps database data)
docker compose down

# Stop and remove persistent volumes (fresh start)
docker compose down -v
```

---

## 📚 Additional Documentation

Deeper notes live under [`docs/`](docs/):

* [Codebase Overview](docs/codebase-overview.md) — how the code is structured internally.
* [Environment Variables Reference](docs/environment-variables.md) — every env var read by the app, including ones not in `.env.example`.
* [Adding a New AWS Service](docs/adding-a-new-aws-service.md) — the schema → service → endpoint → test pattern used for SQS/DynamoDB/Lambda/etc.
* [Troubleshooting](docs/troubleshooting.md) — common gotchas (port conflicts, LocalStack state resets, stale cache, etc.).
* [Architecture Notes](docs/architecture-notes.md) — the reasoning behind non-obvious design choices.
* [Developer Portal Overview](docs/developer-portal-overview.md) — how the static frontend dashboard is assembled and talks to the API.
* [Observability & Load Testing](docs/observability-and-load-testing.md) — how metrics flow from FastAPI through Prometheus/Grafana, and how Locust/the benchmark script generate traffic.
