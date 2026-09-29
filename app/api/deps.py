from typing import Annotated

import asyncpg
import redis.asyncio as aioredis
from fastapi import Depends, Request

from app.core.database import get_db_pool
from app.core.redis import get_redis_client
from app.services.aws import AWSService, get_aws_service
from app.services.s3 import S3Service, get_s3_service


def get_db(request: Request) -> asyncpg.Pool:
    """Dependency that provides the active asyncpg database connection pool."""
    if hasattr(request.app.state, "pool") and request.app.state.pool:
        return request.app.state.pool
    return get_db_pool()


def get_redis(request: Request) -> aioredis.Redis | None:
    """Dependency that provides the active Redis client."""
    if hasattr(request.app.state, "redis") and request.app.state.redis:
        return request.app.state.redis
    return get_redis_client()


# Type-annotated dependency aliases (complies with Ruff B008 and FastAPI best practices)
DbPoolDep = Annotated[asyncpg.Pool, Depends(get_db)]
RedisDep = Annotated[aioredis.Redis | None, Depends(get_redis)]
AWSServiceDep = Annotated[AWSService, Depends(get_aws_service)]
S3ServiceDep = Annotated[S3Service, Depends(get_s3_service)]
