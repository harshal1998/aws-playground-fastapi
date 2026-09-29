import asyncio

import asyncpg

from app.core.config import settings

pool: asyncpg.Pool | None = None


async def connect_to_database() -> asyncpg.Pool:
    """Initializes the PostgreSQL connection pool with connection retries."""
    global pool
    for attempt in range(1, 11):
        try:
            pool = await asyncpg.create_pool(
                settings.DATABASE_URL,
                min_size=settings.DB_POOL_MIN_SIZE,
                max_size=settings.DB_POOL_MAX_SIZE,
            )
            print("Successfully connected to PostgreSQL!")
            break
        except (asyncpg.PostgresError, OSError):
            if attempt == 10:
                raise
            print(f"Waiting for PostgreSQL (attempt {attempt}/10)...")
            await asyncio.sleep(2)

    return pool


async def close_database_connection():
    """Closes the PostgreSQL connection pool."""
    global pool
    if pool:
        await pool.close()
        pool = None


def get_db_pool() -> asyncpg.Pool:
    """Returns the active database pool or raises an exception."""
    if pool is None:
        raise RuntimeError("Database pool is not initialized")
    return pool
