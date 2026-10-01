"""Items service: Redis cache-aside behaviour against fakeredis."""
import asyncio

import fakeredis

from app.schemas.item import ItemCreate
from app.services import items as items_service


def _run(scenario):
    """Runs scenario(redis) on a fresh event loop with a fresh fake Redis."""

    async def main():
        redis = fakeredis.FakeAsyncRedis(decode_responses=True)
        try:
            return await scenario(redis)
        finally:
            await redis.aclose()

    return asyncio.run(main())


def test_get_items_reads_database_then_cache(db):
    """Verify the first list read hits PostgreSQL and the second is served from Redis."""
    db.add("Widget", "9.99")

    async def scenario(redis):
        first = await items_service.get_items(db, redis, limit=5)
        second = await items_service.get_items(db, redis, limit=5)
        return first, second

    first, second = _run(scenario)
    assert first["source"] == "database (PostgreSQL)"
    assert second["source"] == "cache (Redis)"
    assert second["items"] == first["items"]
    assert first["items"][0] == {
        "id": 1,
        "name": "Widget",
        "price": 9.99,
        "is_offer": False,
        "created_at": "2026-01-01T12:00:00",
    }
    assert db.fetch_calls == 1


def test_get_items_caches_each_limit_separately(db):
    """Verify different limits get their own cache entries."""
    for i in range(3):
        db.add(f"Item {i}", "1.00")

    async def scenario(redis):
        two = await items_service.get_items(db, redis, limit=2)
        three = await items_service.get_items(db, redis, limit=3)
        return two, three

    two, three = _run(scenario)
    assert (two["count"], three["count"]) == (2, 3)
    assert three["source"] == "database (PostgreSQL)"
    assert [i["id"] for i in three["items"]] == [3, 2, 1]


def test_create_item_invalidates_cached_lists(db):
    """Verify a create bumps the generation so the next list read sees the new item."""
    db.add("Old", "1.00")

    async def scenario(redis):
        await items_service.get_items(db, redis, limit=10)  # warm the cache
        gen_before = await redis.get(items_service.ITEMS_GEN_KEY)
        created = await items_service.create_item(db, redis, ItemCreate(name="New", price=2.5, is_offer=True))
        gen_after = await redis.get(items_service.ITEMS_GEN_KEY)
        after = await items_service.get_items(db, redis, limit=10)
        return gen_before, gen_after, created, after

    gen_before, gen_after, created, after = _run(scenario)
    assert gen_before is None
    assert gen_after == "1"
    assert created["name"] == "New"
    assert created["price"] == 2.5
    assert after["source"] == "database (PostgreSQL)"
    assert [i["name"] for i in after["items"]] == ["New", "Old"]


def test_list_cache_entries_have_a_ttl(db):
    """Verify cached list entries expire instead of living forever."""
    db.add("Widget", "9.99")

    async def scenario(redis):
        await items_service.get_items(db, redis, limit=5)
        return await redis.ttl("items:gen:0:limit:5")

    ttl = _run(scenario)
    assert 0 < ttl <= items_service.CACHE_TTL_SECONDS


def test_get_item_by_id_reads_database_then_cache(db):
    """Verify a single-item read is cached under item:{id} with a TTL."""
    db.add("Widget", "9.99")

    async def scenario(redis):
        first = await items_service.get_item_by_id(db, redis, 1)
        second = await items_service.get_item_by_id(db, redis, 1)
        ttl = await redis.ttl("item:1")
        return first, second, ttl

    first, second, ttl = _run(scenario)
    assert first == second
    assert first["price"] == 9.99
    assert db.fetchrow_calls == 1
    assert 0 < ttl <= items_service.CACHE_TTL_SECONDS


def test_missing_item_is_not_cached(db):
    """Verify a miss returns None and leaves nothing in Redis."""

    async def scenario(redis):
        result = await items_service.get_item_by_id(db, redis, 42)
        return result, await redis.exists("item:42")

    result, exists = _run(scenario)
    assert result is None
    assert exists == 0


def test_no_redis_client_always_reads_database(db):
    """Verify the service works without Redis, reading PostgreSQL every time."""
    db.add("Widget", "9.99")

    async def scenario():
        for _ in range(2):
            listing = await items_service.get_items(db, None, limit=5)
            assert listing["source"] == "database (PostgreSQL)"
        return await items_service.get_item_by_id(db, None, 1)

    item = asyncio.run(scenario())
    assert item["name"] == "Widget"
    assert db.fetch_calls == 2
