import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    PROJECT_NAME: str = "AWS Playground FastAPI"
    PROJECT_DESCRIPTION: str = (
        "Production-grade local development stack with PostgreSQL, Redis, Mailpit, LocalStack, and Prometheus."
    )
    API_PORT: int = int(os.getenv("API_PORT", "8000"))

    # Database Settings
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "postgrespassword")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "appdb")
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@localhost:5432/{POSTGRES_DB}",
    )
    DB_POOL_MIN_SIZE: int = int(os.getenv("DB_POOL_MIN_SIZE", "5"))
    DB_POOL_MAX_SIZE: int = int(os.getenv("DB_POOL_MAX_SIZE", "20"))

    # Redis Settings
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    # Short timeouts keep the best-effort cache from stalling requests when
    # Redis accepts connections but never answers.
    REDIS_SOCKET_CONNECT_TIMEOUT: float = float(os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT", "1"))
    REDIS_SOCKET_TIMEOUT: float = float(os.getenv("REDIS_SOCKET_TIMEOUT", "1"))

    # Mailpit SMTP Settings
    MAILPIT_HOST: str = os.getenv("MAILPIT_HOST", "localhost")
    MAILPIT_PORT: int = int(os.getenv("MAILPIT_PORT", "1025"))

    # LocalStack / AWS S3 Settings
    AWS_ENDPOINT_URL: str = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
    AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "test")
    AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "test")
    AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")
    S3_BUCKET_NAME: str = os.getenv("S3_BUCKET_NAME", "fastapi-bucket")
    # Keep in sync with client_max_body_size in docker/nginx/nginx.conf.
    S3_MAX_UPLOAD_BYTES: int = int(os.getenv("S3_MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))

    # botocore client timeouts (seconds) and total attempts per call
    AWS_CONNECT_TIMEOUT: float = float(os.getenv("AWS_CONNECT_TIMEOUT", "3"))
    AWS_READ_TIMEOUT: float = float(os.getenv("AWS_READ_TIMEOUT", "30"))
    AWS_MAX_ATTEMPTS: int = int(os.getenv("AWS_MAX_ATTEMPTS", "2"))


settings = Settings()
