# Environment Variables Reference

There are two layers of configuration in this repo, and they don't fully overlap:

1. **`.env`** (copied from `.env.example`) — read by `compose.yml` on the host. Controls
   container credentials and which host ports services are published on.
2. **`app/core/config.py`'s `Settings`** — read *inside* the `api` container at runtime via
   `os.getenv`. Some of these are set by `compose.yml`'s `api.environment:` block (hardcoded to
   Docker service names like `db`, `redis`, `mailpit`, `localstack`), not by `.env` — so editing
   `.env` alone won't change them for the containerized app. They matter most when running the API
   directly on the host (`dev.ps1 run` / bare `uvicorn`), where `localhost` is substituted instead.

## Vars in `.env.example` (host / compose layer)

| Variable | Default | Used by |
| :--- | :--- | :--- |
| `BIND_ADDRESS` | `127.0.0.1` | host interface for every published port; set `0.0.0.0` only on a trusted network |
| `POSTGRES_USER` | `postgres` | `db`, `api`, `migration` |
| `POSTGRES_PASSWORD` | *(placeholder — change it)* | `db`, `api`, `migration` |
| `POSTGRES_DB` | `appdb` | `db`, `api`, `migration` |
| `POSTGRES_PORT` | `5432` | host port mapping for `db` |
| `API_PORT` | `8000` | host port mapping for `api` |
| `DATABASE_URL` | built from the Postgres vars above | overridable full DSN for `api` |
| `LOCUST_PORT` | `8089` | host port mapping for `locust` |
| `PGADMIN_DEFAULT_EMAIL` | `admin@admin.com` | `pgadmin` login |
| `PGADMIN_DEFAULT_PASSWORD` | *(placeholder — change it)* | `pgadmin` login |
| `PGADMIN_PORT` | `5050` | host port mapping for `pgadmin` |
| `REDIS_PORT` | `6379` | host port mapping for `redis` |
| `REDIS_URL` | `redis://redis:6379/0` | overridable full URL for `api` |
| `REDIS_COMMANDER_PORT` | `8081` | host port mapping for `redis-commander` |
| `PROMETHEUS_PORT` | `9090` | host port mapping for `prometheus` |
| `GRAFANA_PORT` | `3000` | host port mapping for `grafana` |
| `MAILPIT_SMTP_PORT` | `1025` | host port mapping for `mailpit` SMTP |
| `MAILPIT_UI_PORT` | `8025` | host port mapping for `mailpit` web UI |
| `LOCALSTACK_PORT` | `4566` | host port mapping for `localstack` |
| `S3_BROWSER_PORT` | `8085` | host port mapping for `s3-browser` |
| `S3_BROWSER_USER` | `admin` | `s3-browser` login |
| `S3_BROWSER_PASS` | `admin` | `s3-browser` login |
| `GATEWAY_PORT` | `80` | host port mapping for `nginx` |

## Vars read by `Settings` but **not** in `.env.example`

These exist in `app/core/config.py` and have code-level defaults. Some are overridden inside
`compose.yml`'s `api.environment:` block (marked below); the rest fall back to their hardcoded
default in every environment, including inside Docker.

| Variable | Default in `Settings` | Overridden in `compose.yml`? |
| :--- | :--- | :--- |
| `DB_POOL_MIN_SIZE` | `5` | no |
| `DB_POOL_MAX_SIZE` | `20` | no |
| `REDIS_SOCKET_CONNECT_TIMEOUT` | `1` (seconds) | no |
| `REDIS_SOCKET_TIMEOUT` | `1` (seconds) — a slower Redis reply is treated as a cache miss | no |
| `MAILPIT_HOST` | `localhost` | yes → `mailpit` |
| `MAILPIT_PORT` | `1025` | yes → `1025` (same value, set explicitly) |
| `AWS_ENDPOINT_URL` | `http://localhost:4566` | yes → `http://localstack:4566` |
| `AWS_ACCESS_KEY_ID` | `test` | no (LocalStack accepts any value) |
| `AWS_SECRET_ACCESS_KEY` | `test` | no (LocalStack accepts any value) |
| `AWS_REGION` | `us-east-1` | no |
| `S3_BUCKET_NAME` | `fastapi-bucket` | no |
| `S3_MAX_UPLOAD_BYTES` | `10485760` (10 MiB) — cap for `POST /s3/upload` and `/s3/upload-text`; keep nginx's `client_max_body_size` in sync | no |
| `AWS_CONNECT_TIMEOUT` | `3` (seconds, botocore connect timeout) | no |
| `AWS_READ_TIMEOUT` | `30` (seconds, botocore read timeout) | no |
| `AWS_MAX_ATTEMPTS` | `2` (total attempts per boto3 call, incl. the first) | no |

**Practical implication:** if you run the API in Docker, `MAILPIT_HOST` and `AWS_ENDPOINT_URL` are
always the Docker service names regardless of `.env` — you cannot change them via `.env` without
also editing `compose.yml`. If you run the API on the host (`dev.ps1 run`), `dev.ps1` sets
`DATABASE_URL`, `REDIS_URL`, `MAILPIT_HOST`, and `AWS_ENDPOINT_URL` to `localhost`-based values
itself, bypassing `.env` entirely for those four.

## `LOCALSTACK` service enablement

Not an app-level `Settings` var, but worth knowing: `compose.yml`'s `localstack.environment` sets
`SERVICES=s3,sqs,sns,dynamodb,secretsmanager,ssm,lambda,events,kinesis`. If you add a new AWS
service integration (see
[Adding a new AWS service](adding-a-new-aws-service.md)) and it isn't in that list, LocalStack
won't enable it and calls will fail even though the SDK code is correct.
