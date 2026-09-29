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

## Hand-rolled `Settings` dataclass instead of `pydantic-settings`

`app/core/config.py` uses a `@dataclass(frozen=True)` reading `os.getenv()` directly rather than
`pydantic-settings`'s `BaseSettings`. This works fine for a small, fixed set of env vars with
simple string/int types, and avoids an extra dependency. It does mean:
- No automatic `.env` file loading — env vars must be present in the process environment (Docker
  Compose provides this; running bare `uvicorn` on the host requires `.env` to be sourced some
  other way, which is why `dev.ps1 run` sets required vars inline as `$env:` before starting
  Uvicorn).
- No validation beyond Python's own type coercion (`int(os.getenv(...))` will raise a raw
  `ValueError` on a malformed value, not a friendly Pydantic validation error).

## Dual `items` table creation (Alembic *and* `database.py`)

Both `app/alembic/versions/001_create_items_table.py` and
`connect_to_database()` in `app/core/database.py` run the same
`CREATE TABLE IF NOT EXISTS items (...)`. This looks redundant, and functionally it is for the
current schema — but it serves two different audiences:
- `database.py`'s inline DDL guarantees the API works out of the box even if someone forgets to
  run `docker compose run --rm migration` — appropriate for a "playground" repo where quick
  start matters more than migration discipline.
- The Alembic migration exists so the **pattern** of doing schema changes through migrations is
  demonstrated and available, per the project's stated goal of being a hands-on
  learning/practice environment for production patterns (per `README.md`).

If you add a column to `items`, you must update **both** places, or accept that the Alembic
migration becomes stale documentation. There is no automated check enforcing they stay in sync.

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

`RedisDep` can resolve to `None` (see `app/api/deps.py`), and every caller
(`items_service.get_items`, `get_item_by_id`, `create_item`) checks `if redis_client:` before
using it, falling back to direct Postgres reads/writes. Postgres, by contrast, has no such
fallback — `DbPoolDep` always returns a pool or raises. This reflects Redis's role in this repo as
a demonstrable *cache* (optional, degrades gracefully) versus Postgres as the *source of truth*
(required). Keep this asymmetry in mind if adding new cached data — the pattern is "cache-aside
with graceful degradation," not "cache-required."

## No authentication/authorization anywhere

There is no auth middleware, API key check, or user model in the app. This is consistent with the
project's purpose (a local playground exposed at `localhost`, fronted by Nginx with no TLS) —
not an oversight to "fix," but also not a pattern to carry over if this code is ever used as a
starting point for something internet-facing.
