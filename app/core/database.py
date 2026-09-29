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

    # Ensure items table exists
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                price NUMERIC(10, 2) NOT NULL,
                is_offer BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
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
