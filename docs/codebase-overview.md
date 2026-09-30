# Codebase Overview

Notes from an initial exploration of the repo, for quick orientation. See `README.md` for
setup/usage instructions — this file focuses on how the code is structured internally.

## What this project is

A local, Docker-orchestrated **AWS/backend playground** built for learning/practicing production
patterns — not a real deployed service. It's a FastAPI app plus an 11-service `compose.yml` stack.

## Core app (`app/`)

- **`main.py`** — FastAPI app with lifespan hooks: opens the Postgres pool, connects Redis,
  ensures the S3 bucket exists on startup; adds a Prometheus metrics middleware; exposes `/metrics`.
- **`core/`** — thin infra wrappers:
  - `database.py` — asyncpg pool with retry-loop connect (no DDL; tables come from Alembic).
  - `redis.py` — redis.asyncio client with retry.
  - `metrics.py` — request counter + latency histogram middleware.
  - `config.py` — a frozen dataclass `Settings` reading env vars (no pydantic-settings).
- **`api/`**:
  - `deps.py` — typed `Annotated[..., Depends(...)]` aliases (`DbPoolDep`, `RedisDep`,
    `AWSServiceDep`, `S3ServiceDep`).
  - `v1/router.py` — wires up `root`, `items`, `s3`, `aws` sub-routers.
- **`services/`**:
  - `items.py` — plain functions implementing **cache-aside** against Redis (60s TTL) with
    Postgres fallback; list keys embed a generation counter (`items:gen:{gen}:limit:{limit}`) and a
    create invalidates them with a single `INCR items:gen` (no key scan; stale keys expire via TTL).
  - `s3.py` — class-based `S3Service` (singleton via `get_s3_service()`), boto3 client pointed at
    LocalStack, bucket ensure/list/get/put/delete.
  - `aws.py` — larger class-based `AWSService` wrapping SQS, DynamoDB, Secrets Manager, Lambda
    (zips code on the fly), EventBridge, and Kinesis — all against LocalStack, all with broad
    `except Exception` swallowing that returns empty lists/defaults rather than propagating.
  - `email.py` — fire-and-forget SMTP to Mailpit, used as a FastAPI `BackgroundTask` on item
    creation.
- **`tests/test_api.py`** — integration tests (not unit tests) that hit a **live running stack**
  via `requests`, covering items CRUD/cache, S3, and every AWS service lifecycle (SQS, DynamoDB,
  EventBridge, Kinesis, Lambda).
- **`alembic/`** — one migration (`001_create_items_table`), the only place the `items` table
  is created; the `api` container runs `alembic upgrade head` on every start.

## Infrastructure (`compose.yml`, `docker/`)

11 services: Postgres + pgAdmin, Redis + Redis Commander, Mailpit, LocalStack
(S3/SQS/SNS/DynamoDB/SecretsManager/SSM/Lambda/Events/Kinesis) + a third-party S3 browser UI
("Sairo"), Prometheus + Grafana, the FastAPI `api` itself, Nginx (reverse proxy + serves a static
vanilla-JS "Developer Portal" at `docker/portal/`), Locust (load testing), plus profile-gated
`test` and `migration` one-shot containers.

## Notable observations

- Not a git repo as of this writing — no version history to check.
- `config.py`'s `DATABASE_URL` default embeds `POSTGRES_USER`/`PASSWORD` at class-definition time
  as dataclass field defaults — works, but relies on field evaluation order within the dataclass
  body.
- `aws.py` has a lot of repeated `try/except Exception: print(...); return []` boilerplate across
  list operations — a candidate for simplification if consolidating error handling.
- Tests require the full stack running (`docker compose up`) — they're integration, not isolated
  unit tests.
