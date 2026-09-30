import asyncio
import datetime
from decimal import Decimal

import redis.asyncio as aioredis

from app.schemas.item import ItemCreate
from app.services import items as items_service

# ------------------------------------------------------------------------------
# Redis outage: the items cache must be best-effort
# ------------------------------------------------------------------------------
# Stopping the shared redis container mid-suite would break the other tests,
# so these drive the service layer directly with a Redis client that fails
# every call, and a stub PostgreSQL connection.

ROW = {
    "id": 1,
    "name": "Cache Outage Item",
    "price": Decimal("9.99"),
    "is_offer": False,
    "created_at": datetime.datetime(2026, 1, 1),
}


class FailingRedis:
    """Redis client stub whose every call raises a connection error."""

    def _fail(self, *args, **kwargs):
        raise aioredis.ConnectionError("Error connecting to redis:6379. Connection refused.")

    async def get(self, *args, **kwargs):
        self._fail()

    async def setex(self, *args, **kwargs):
        self._fail()

    async def delete(self, *args, **kwargs):
        self._fail()

    async def scan_iter(self, *args, **kwargs):
        self._fail()
        yield  # pragma: no cover - makes this an async generator


class StubConn:
    async def fetchrow(self, *args):
        return ROW

    async def fetch(self, *args):
        return [ROW]


class StubAcquire:
    async def __aenter__(self):
        return StubConn()

    async def __aexit__(self, *exc):
        return False


class StubPool:
    def acquire(self):
        return StubAcquire()


def test_get_items_falls_back_to_postgres_when_redis_fails():
    """Verify listing items serves from PostgreSQL when Redis raises."""
    result = asyncio.run(items_service.get_items(StubPool(), FailingRedis(), limit=5))
    assert result["source"] == "database (PostgreSQL)"
    assert result["count"] == 1
    assert result["items"][0]["name"] == ROW["name"]


def test_get_item_by_id_falls_back_to_postgres_when_redis_fails():
    """Verify reading one item serves from PostgreSQL when Redis raises."""
    result = asyncio.run(items_service.get_item_by_id(StubPool(), FailingRedis(), 1))
    assert result["id"] == 1
    assert result["price"] == 9.99


def test_create_item_succeeds_when_cache_invalidation_fails():
    """Verify a failed cache invalidation does not fail item creation."""
    item = ItemCreate(name=ROW["name"], price=9.99, is_offer=False)
    result = asyncio.run(items_service.create_item(StubConn(), FailingRedis(), item))
    assert result["id"] == 1
    assert result["name"] == ROW["name"]
