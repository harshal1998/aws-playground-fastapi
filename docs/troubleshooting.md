# Troubleshooting

Gotchas found while reading the code — not exhaustive, but covers the sharp edges baked into how
this stack is wired up.

## Port conflicts on startup

The 12 long-running services publish 13 host ports between them (Mailpit publishes two; see
`docs/environment-variables.md` for the full list), all on `BIND_ADDRESS` (`127.0.0.1` by
default). If `docker compose up -d` fails or a container won't come up, check for a local
process already bound to one of: `80, 3000, 4566, 5050, 5432, 6379, 8000, 8025, 8081, 8085, 8089, 9090, 1025`.
Override the conflicting port via `.env` rather than editing `compose.yml`.

## Services unreachable from another machine or VM

That's intentional: ports bind to `127.0.0.1` unless `BIND_ADDRESS` in `.env` says otherwise.
Set `BIND_ADDRESS=0.0.0.0` (then `docker compose up -d` to recreate the containers) only on a
trusted network — the API is unauthenticated and can deploy Lambda code.

## API container can't reach Postgres/Redis on startup

`app/core/database.py` and `app/core/redis.py` both retry up to 10 times (2s apart) before
raising. This is normal on a cold `docker compose up` — Postgres/Redis take a few seconds to
become healthy and `api` has a `depends_on: condition: service_healthy` guard, but the retry loop
is a second line of defense. If it still fails after ~20s the `api` process exits and Compose
restarts it (`restart: unless-stopped`), so a restart loop in `docker compose ps` points here
too. Check `docker compose logs db redis`
for the actual failure (e.g. a bad `POSTGRES_PASSWORD` mismatch between `.env` and an existing
`postgres_data` volume from a previous run — Postgres won't re-initialize credentials on an
existing volume).

## AWS/LocalStack calls fail with "service not available"

LocalStack only enables the services listed in `compose.yml`'s
`localstack.environment: SERVICES=...`. If you're getting connection or 501-style errors for a
service that looks correctly implemented in `app/services/aws.py`, check that the service name is
actually in that list — see
[Adding a New AWS Service](adding-a-new-aws-service.md).

## LocalStack state resets

LocalStack's in-memory/local state (S3 buckets, SQS queues, DynamoDB tables, etc.) lives inside
the `localstack` container, **not** in a named volume in `compose.yml`. That means:
- `docker compose restart localstack` or `docker compose down` (without `-v`) may still lose
  LocalStack state depending on LocalStack's persistence settings — treat anything created in
  LocalStack as ephemeral.
- `app/main.py`'s lifespan calls `get_s3_service().ensure_bucket_exists()` on every API startup,
  so the S3 bucket is recreated automatically *when the API starts*. If LocalStack is
  unreachable at that moment the API logs it and starts anyway without the bucket, and a
  LocalStack restart after the API is up also loses it; in both cases run
  `docker compose restart api` once LocalStack is healthy. Other resources (SQS queues, DynamoDB
  tables, Lambda functions) are not — you'll need to recreate them (or rerun
  `docker compose run --rm test`, which exercises the full lifecycle) after a LocalStack restart.

## `s3-browser` (Sairo) container fails or won't authenticate

`compose.yml` sets `JWT_SECRET=${JWT_SECRET:-sairo-secret-key-fixed-32-chars-long}` — if you
override `JWT_SECRET` in `.env`, it must still meet Sairo's minimum key length requirement or the
container will fail to start/sign tokens. Login is `S3_BROWSER_USER`/`S3_BROWSER_PASS`
(default `admin`/`admin`), not tied to LocalStack credentials.

## `dev.ps1` is Windows-only

`dev.ps1` is a PowerShell script; on Linux/macOS use the equivalent `docker compose` commands
directly (each `dev.ps1` action is a one-line wrapper — see the script itself for the exact
commands, e.g. `test` → `docker compose run --rm test`).

## Redis cache looks stale / `GET /items` won't reflect a new item

`items_service.create_item` invalidates cached lists by running `INCR items:gen`; list keys embed
that generation (`items:gen:{gen}:limit:{limit}`), so older entries are simply never read again. If
Redis is unreachable at write time, `redis_client` is falsy and the invalidation is silently
skipped (by design — the app treats Redis as optional, degrading to direct-DB reads). If you added
an item and still see a stale cached list, check `redis_client` connectivity rather than assuming
a cache bug — `RedisDep` returns `None` rather than raising when Redis isn't connected.

## Running tests locally without Docker

Almost all of `app/tests/` is integration tests — real HTTP calls via `requests` against
`API_URL` (default `http://localhost:8000`) — so the full stack (`docker compose up -d`) must
already be running. Running `pytest` directly on the host works like
`docker compose run --rm test` as long as the API is reachable at `API_URL` and the app's
dependencies (`requirements.txt`) are installed: `test_s3_and_cache.py` imports `app` to drive
the Redis-outage tests with stub clients.

## `relation "items" does not exist`

Tables are created only by Alembic migrations (`alembic upgrade head`);
`app/core/database.py` just opens the connection pool and never creates tables. The `api`
container runs `alembic upgrade head` on every start (see its `command` in `compose.yml`), so
this error normally means the API is running *outside* that container (`dev.ps1 run`, bare
`uvicorn`, or an overridden command) against a database that was never migrated. Run
`docker compose run --rm migration` (or `.\dev.ps1 migrate`) and retry. See
[Architecture Notes](architecture-notes.md#schema-is-owned-by-alembic-only).
