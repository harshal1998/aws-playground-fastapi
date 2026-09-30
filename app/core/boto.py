"""Shared botocore configuration for every boto3 client in the app."""
from botocore.config import Config

from app.core.config import settings

# Without explicit timeouts botocore waits ~60 s per attempt (and retries),
# blocking a worker thread whenever LocalStack is down or unreachable.
BOTO_CLIENT_CONFIG = Config(
    connect_timeout=settings.AWS_CONNECT_TIMEOUT,
    read_timeout=settings.AWS_READ_TIMEOUT,
    retries={"max_attempts": settings.AWS_MAX_ATTEMPTS, "mode": "standard"},
)
