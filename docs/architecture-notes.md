# Architecture Notes

Observations on *why* the code is structured the way it is, inferred from reading it — this is not
an authoritative design doc, just documented reasoning to help a future contributor understand
patterns before "fixing" something that's intentional.

## Class-based services (S3, AWS) vs. plain-function services (items, email)

`S3Service` and `AWSService` are classes with `cached_property` boto3 clients and a
module-level singleton (`get_s3_service()` / `get_aws_service()`), while `items.py` and
`email.py` are plain functions taking a connection/client as an argument.

Likely reasoning: S3/AWS integrations need to lazily construct and cache several boto3 clients
per service (SQS, DynamoDB, Lambda, etc.) — a class is a natural place to hold that state. Items
and email have no client-construction cost worth caching (`asyncpg`/Redis connections are already
managed centrally via `app/core/database.py` / `app/core/redis.py` and passed in through FastAPI
`Depends`), so plain functions avoid unnecessary ceremony. If you're adding a new integration that
needs a stateful client, follow the class pattern; if it's pure business logic over an
already-injected connection, follow the function pattern.

## `pydantic-settings` for `Settings`

`app/core/config.py` is a `pydantic-settings` `BaseSettings` class. Fields keep the same env var
names and defaults the earlier hand-rolled dataclass had, and `settings.X` access is unchanged.
It adds:
- `.env` loading from the working directory. Real env vars still win, so compose.yml's
  `api.environment` block and `dev.ps1 run`'s inline `$env:` values take precedence. Note that a
  bare host `uvicorn` now picks up `.env.example`'s container-oriented `REDIS_URL=redis://redis:...`
  if you copied it; override it or use `dev.ps1 run`.
- Validation at startup: a malformed value raises a pydantic `ValidationError` naming the variable.
- `DATABASE_URL` still defaults to a `localhost` DSN built from the `POSTGRES_*` values.

## Schema is owned by Alembic only

The `items` table is created by `app/alembic/versions/001_create_items_table.py` and nothing
else: `connect_to_database()` in `app/core/database.py` only opens the asyncpg pool and runs no
DDL. The out-of-the-box experience comes from `compose.yml` instead — the `api` service's
command runs `alembic upgrade head` before starting Uvicorn, so the schema is current on every
container start.

If you add a column or table, write a new Alembic migration; there is no second copy of the DDL
to keep in sync. When running the API outside the `api` container (`dev.ps1 run`, bare
`uvicorn`), apply migrations first with `docker compose run --rm migration` (or
`.\dev.ps1 migrate`).

## Broad `except Exception` in `AWSService` list operations

Every `list_*` method in `app/services/aws.py` (SQS, DynamoDB, Lambda, EventBridge, Kinesis)
catches `Exception` broadly, logs via `print()`, and returns an empty list/dict instead of
propagating. This trades error visibility for a resilient portal UI — the Developer Portal's AWS
Explorer tab can render "0 queues" instead of crashing if LocalStack is still starting up or a
particular service isn't enabled in `SERVICES=`. Mutating operations (create/put/delete) largely
do **not** swallow exceptions the same way — they let `ClientError` propagate up to the endpoint,
which converts it to an `HTTPException(400, ...)`, since a failed write needs to surface to the
caller.

## Redis and Postgres treated as fault-tolerant dependencies

`RedisDep` can resolve to `None` (see `app/api/deps.py`), and `items_service.get_items`,
`get_item_by_id` and `create_item` only touch Redis through small helpers in
`app/services/items.py` that skip the call when the client is `None` and catch Redis errors
(including timeouts, bounded by `REDIS_SOCKET_TIMEOUT`), logging a warning and falling back to
direct Postgres reads/writes. So a Redis outage *while the API is running* never fails a
request. (Redis must still be reachable when the API *starts*: `connect_to_redis()` retries and
then raises.) Postgres, by contrast, has no such fallback — `DbPoolDep` always returns a pool
or raises. This reflects Redis's role in this repo as
a demonstrable *cache* (optional, degrades gracefully) versus Postgres as the *source of truth*
(required). Keep this asymmetry in mind if adding new cached data — the pattern is "cache-aside
with graceful degradation," not "cache-required."

## No authentication/authorization anywhere

There is no auth middleware, API key check, or user model in the app. This is consistent with the
project's purpose (a local playground exposed at `localhost`, fronted by Nginx with no TLS) —
not an oversight to "fix," but also not a pattern to carry over if this code is ever used as a
starting point for something internet-facing. The compensating control is network exposure:
every published port in `compose.yml` binds to `BIND_ADDRESS` (default `127.0.0.1`), so only
the local machine can reach the API, which can deploy Lambda code, and LocalStack, which has
the Docker socket mounted. Setting `BIND_ADDRESS=0.0.0.0` removes that control.
