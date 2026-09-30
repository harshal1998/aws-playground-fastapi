# Codebase Overview

Notes from an initial exploration of the repo, for quick orientation. See `README.md` for
setup/usage instructions — this file focuses on how the code is structured internally.

## What this project is

A local, Docker-orchestrated **AWS/backend playground** built for learning/practicing production
patterns — not a real deployed service. It's a FastAPI app plus a `compose.yml` stack of 12
services and two profile-gated one-shot services.

## Core app (`app/`)

- **`main.py`** — FastAPI app with lifespan hooks: opens the Postgres pool, connects Redis,
  ensures the S3 bucket exists on startup (logs and carries on if LocalStack is unreachable);
  adds a Prometheus metrics middleware; exposes `/metrics`.
- **`core/`** — thin infra wrappers:
  - `database.py` — asyncpg pool with retry-loop connect (no DDL; tables come from Alembic).
  - `redis.py` — redis.asyncio client with retry and short socket timeouts
    (`REDIS_SOCKET_CONNECT_TIMEOUT` / `REDIS_SOCKET_TIMEOUT`, 1s each).
  - `boto.py` — shared botocore `Config` (connect/read timeouts, retry attempts) for every boto3
    client.
  - `metrics.py` — request counter + latency histogram middleware, labelled by route template;
    aggregates all uvicorn workers when `PROMETHEUS_MULTIPROC_DIR` is set.
  - `config.py` — a `pydantic-settings` `Settings` class: typed, validated env vars, plus `.env`
    loading.
  - `logging_config.py` — sends the app's `app.*` loggers to stderr with level and logger name.
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
    (zips code on the fly), EventBridge, and Kinesis — all against LocalStack. List operations
    follow every page; Kinesis reads cover every shard. boto3 errors propagate to the handlers
    in `api/errors.py`, which map them to 404/400/409/429/502/503.
  - `email.py` — fire-and-forget SMTP to Mailpit, used as a FastAPI `BackgroundTask` on item
    creation.
- **`tests/`** — mostly integration tests that hit a **live running stack** via `requests`:
  `test_api.py` (items CRUD/cache, S3, and the SQS, DynamoDB, EventBridge, Kinesis and Lambda
  lifecycles), `test_items_validation.py` (422 input limits), `test_aws_lambda_dynamodb.py`
  (Lambda errors/redeploys, DynamoDB native types) and `test_s3_and_cache.py` (S3 upload
  limits/downloads, plus Redis-outage tests that call `app/services/items.py` directly with
  stub Redis/Postgres clients).
- **`alembic/`** — one migration (`001_create_items_table`), the only place the `items` table
  is created; the `api` container runs `alembic upgrade head` on every start.

## Infrastructure (`compose.yml`, `docker/`)

12 services: Postgres + pgAdmin, Redis + Redis Commander, Mailpit, LocalStack
(S3/SQS/SNS/DynamoDB/SecretsManager/SSM/Lambda/Events/Kinesis) + a third-party S3 browser UI
("Sairo"), Prometheus + Grafana, the FastAPI `api` itself, Nginx (reverse proxy + serves a static
vanilla-JS "Developer Portal" at `docker/portal/`), Locust (load testing), plus profile-gated
`test` and `migration` one-shot containers.

## Notable observations

- Tests require the full stack running (`docker compose up`) — almost all are integration tests;
  only the stubbed Redis-outage tests in `test_s3_and_cache.py` run without the stack (they
  still need the app's Python dependencies installed).
