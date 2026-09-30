import json
import logging
import socket

import asyncpg
import redis.asyncio as aioredis

from app.schemas.item import ItemCreate

logger = logging.getLogger(__name__)

# The cache is best-effort: any of these from Redis must never fail a request.
CACHE_ERRORS = (aioredis.RedisError, OSError)

CACHE_TTL_SECONDS = 60

# Generation counter for the items-list cache (see _items_generation).
ITEMS_GEN_KEY = "items:gen"


async def _cache_get(redis_client: aioredis.Redis | None, key: str) -> str | None:
    """Reads a cache key, returning None on a miss or if Redis is unavailable."""
    if not redis_client:
        return None
    try:
        return await redis_client.get(key)
    except CACHE_ERRORS as e:
        logger.warning("Redis cache read failed for %s, falling back to PostgreSQL: %s", key, e)
        return None


async def _cache_set(redis_client: aioredis.Redis | None, key: str, value: dict) -> None:
    """Writes a cache key with a TTL, ignoring Redis failures."""
    if not redis_client:
        return
    try:
        await redis_client.setex(key, CACHE_TTL_SECONDS, json.dumps(value))
    except CACHE_ERRORS as e:
        logger.warning("Redis cache write failed for %s: %s", key, e)


async def _items_generation(redis_client: aioredis.Redis | None) -> str | None:
    """Returns the current items-list cache generation, or None to bypass the cache.

    List cache keys embed this counter, so bumping it on a write makes every
    older list entry unreachable at once (they then expire via their TTL)
    without scanning the keyspace.
    """
    if not redis_client:
        return None
    try:
        return await redis_client.get(ITEMS_GEN_KEY) or "0"
    except CACHE_ERRORS as e:
        logger.warning("Redis read of %s failed, bypassing the items cache: %s", ITEMS_GEN_KEY, e)
        return None


async def _cache_invalidate_items(redis_client: aioredis.Redis | None) -> None:
    """Invalidates cached item lists by bumping the generation, ignoring Redis failures.

    Per-item item:{id} entries are left alone: a create never makes them stale.
    """
    if not redis_client:
        return
    try:
        await redis_client.incr(ITEMS_GEN_KEY)
    except CACHE_ERRORS as e:
        logger.warning("Redis cache invalidation failed: %s", e)


async def create_item(
    conn: asyncpg.Connection,
    redis_client: aioredis.Redis | None,
    item: ItemCreate,
) -> dict:
    """Inserts a new item into PostgreSQL and invalidates the Redis items cache."""
    row = await conn.fetchrow(
        """
        INSERT INTO items (name, price, is_offer)
        VALUES ($1, $2, $3)
        RETURNING id, name, price, is_offer, created_at
        """,
        item.name,
        item.price,
        item.is_offer,
    )

    await _cache_invalidate_items(redis_client)

    return {
        "id": row["id"],
        "name": row["name"],
        "price": float(row["price"]),
        "is_offer": row["is_offer"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


async def get_items(
    pool: asyncpg.Pool,
    redis_client: aioredis.Redis | None,
    limit: int = 10,
) -> dict:
    """Retrieves items using Redis Cache-Aside pattern falling back to PostgreSQL."""
    generation = await _items_generation(redis_client)
    # generation is None when Redis is unavailable: read straight from PostgreSQL.
    cache_key = f"items:gen:{generation}:limit:{limit}"
    cache_client = redis_client if generation is not None else None

    cached_data = await _cache_get(cache_client, cache_key)
    if cached_data:
        data = json.loads(cached_data)
        return {
            "source": "cache (Redis)",
            "count": data["count"],
            "items": data["items"],
            "container_id": socket.gethostname(),
        }

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, name, price, is_offer, created_at
            FROM items
            ORDER BY id DESC
            LIMIT $1
            """,
            limit,
        )

        items = [
            {
                "id": r["id"],
                "name": r["name"],
                "price": float(r["price"]),
                "is_offer": r["is_offer"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]

        result = {"count": len(items), "items": items}

        await _cache_set(cache_client, cache_key, result)

        return {
            "source": "database (PostgreSQL)",
            "count": result["count"],
            "items": result["items"],
            "container_id": socket.gethostname(),
        }


async def get_item_by_id(
    pool: asyncpg.Pool,
    redis_client: aioredis.Redis | None,
    item_id: int,
) -> dict | None:
    """Retrieves a single item by ID, checking cache first."""
    cache_key = f"item:{item_id}"

    cached_item = await _cache_get(redis_client, cache_key)
    if cached_item:
        return json.loads(cached_item)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, name, price, is_offer, created_at
            FROM items
            WHERE id = $1
            """,
            item_id,
        )
        if not row:
            return None

        item_data = {
            "id": row["id"],
            "name": row["name"],
            "price": float(row["price"]),
            "is_offer": row["is_offer"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        }

        await _cache_set(redis_client, cache_key, item_data)

        return item_data
