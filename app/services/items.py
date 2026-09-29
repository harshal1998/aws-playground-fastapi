import json
import socket

import asyncpg
import redis.asyncio as aioredis

from app.schemas.item import ItemCreate


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

    if redis_client:
        keys = [key async for key in redis_client.scan_iter(match="items:*")]
        if keys:
            await redis_client.delete(*keys)

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
    cache_key = f"items:limit:{limit}"

    if redis_client:
        cached_data = await redis_client.get(cache_key)
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

        if redis_client:
            await redis_client.setex(cache_key, 60, json.dumps(result))

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

    if redis_client:
        cached_item = await redis_client.get(cache_key)
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

        if redis_client:
            await redis_client.setex(cache_key, 60, json.dumps(item_data))

        return item_data
