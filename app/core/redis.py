import asyncio
import logging

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

redis_client: aioredis.Redis | None = None


async def connect_to_redis() -> aioredis.Redis:
    """Connects to Redis with retry logic."""
    global redis_client
    for attempt in range(1, 11):
        try:
            redis_client = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
                socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
            )
            await redis_client.ping()
            logger.info("Connected to Redis")
            break
        except (aioredis.RedisError, OSError) as e:
            if attempt == 10:
                raise
            logger.warning("Waiting for Redis (attempt %d/10): %s", attempt, e)
            await asyncio.sleep(2)
    return redis_client


async def close_redis_connection():
    """Closes the Redis connection."""
    global redis_client
    if redis_client:
        await redis_client.aclose()
        redis_client = None


def get_redis_client() -> aioredis.Redis | None:
    """Returns the current Redis client instance."""
    return redis_client
