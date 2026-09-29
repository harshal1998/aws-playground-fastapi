from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import close_database_connection, connect_to_database
from app.core.metrics import PrometheusMetricsMiddleware, get_metrics_response
from app.core.redis import close_redis_connection, connect_to_redis
from app.services.s3 import get_s3_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Connect to PostgreSQL
    app.state.pool = await connect_to_database()

    # 2. Connect to Redis
    app.state.redis = await connect_to_redis()

    # 3. Ensure LocalStack S3 bucket exists
    get_s3_service().ensure_bucket_exists()

    yield

    # Clean up connections
    await close_database_connection()
    await close_redis_connection()


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.PROJECT_DESCRIPTION,
    lifespan=lifespan,
)

# Prometheus Metrics Middleware
app.add_middleware(PrometheusMetricsMiddleware)


# Prometheus Scrape Endpoint
@app.get("/metrics", tags=["Observability"])
def metrics():
    """Exposes Prometheus metrics endpoint."""
    return get_metrics_response()


# Include v1 API routes
app.include_router(api_router)
