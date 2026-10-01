"""
Application settings, loaded once at import time.

Every field is read from the environment variable of the same name, then
from a `.env` file in the working directory, then falls back to the default
below. Real environment variables win over `.env` (so compose.yml's
`api.environment` block and `dev.ps1 run` still take precedence). A value
that doesn't fit its type or bounds (e.g. `API_PORT=abc`) fails at startup
with a pydantic ValidationError naming the variable.
"""
import os
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

ENV_FILE = ".env"


def _readable_env_file() -> str | None:
    """Returns ENV_FILE if it can be read, else None (skip it).

    The api container runs as a non-root user with the repo bind-mounted,
    so a host .env with mode 600 exists but can't be read there; reading it
    would crash startup, while compose.yml passes the values the container
    needs as real env vars anyway.
    """
    return ENV_FILE if os.access(ENV_FILE, os.R_OK) else None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_readable_env_file(),
        env_file_encoding="utf-8",
        # .env also holds compose-only keys (ports, UI credentials, ...)
        extra="ignore",
        frozen=True,
    )

    PROJECT_NAME: str = "AWS Playground FastAPI"
    PROJECT_DESCRIPTION: str = (
        "Local development and learning stack with PostgreSQL, Redis, Mailpit, LocalStack, and Prometheus."
    )
    API_PORT: int = Field(8000, ge=1, le=65535)
    # Level of the app's own app.* loggers (see app/core/logging_config.py)
    LOG_LEVEL: LogLevel = "INFO"

    # Database Settings
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgrespassword"  # noqa: S105  # local compose default, overridden by .env
    POSTGRES_DB: str = "appdb"
    # Defaults to a localhost DSN built from the POSTGRES_* values above.
    DATABASE_URL: str = ""
    DB_POOL_MIN_SIZE: int = Field(5, ge=0)
    DB_POOL_MAX_SIZE: int = Field(20, ge=1)

    # Redis Settings
    REDIS_URL: str = "redis://localhost:6379/0"
    # Short timeouts keep the best-effort cache from stalling requests when
    # Redis accepts connections but never answers.
    REDIS_SOCKET_CONNECT_TIMEOUT: float = Field(1, gt=0)
    REDIS_SOCKET_TIMEOUT: float = Field(1, gt=0)

    # Mailpit SMTP Settings
    MAILPIT_HOST: str = "localhost"
    MAILPIT_PORT: int = Field(1025, ge=1, le=65535)

    # LocalStack / AWS S3 Settings
    AWS_ENDPOINT_URL: str = "http://localhost:4566"
    AWS_ACCESS_KEY_ID: str = "test"
    AWS_SECRET_ACCESS_KEY: str = "test"  # noqa: S105  # LocalStack dummy credential
    AWS_REGION: str = "us-east-1"
    S3_BUCKET_NAME: str = "fastapi-bucket"
    # Keep in sync with client_max_body_size in docker/nginx/nginx.conf.
    S3_MAX_UPLOAD_BYTES: int = Field(10 * 1024 * 1024, gt=0)

    # botocore client timeouts (seconds) and total attempts per call
    AWS_CONNECT_TIMEOUT: float = Field(3, gt=0)
    AWS_READ_TIMEOUT: float = Field(30, gt=0)
    AWS_MAX_ATTEMPTS: int = Field(2, ge=1)

    @field_validator("LOG_LEVEL", mode="before")
    @classmethod
    def _upper_log_level(cls, value: Any) -> Any:
        return value.upper() if isinstance(value, str) else value

    @model_validator(mode="before")
    @classmethod
    def _default_database_url(cls, data: Any) -> Any:
        """Builds DATABASE_URL from the POSTGRES_* values when it isn't set."""
        if not isinstance(data, dict) or data.get("DATABASE_URL"):
            return data
        fields = cls.model_fields

        def value(name: str) -> Any:
            return data[name] if name in data else fields[name].default

        return {
            **data,
            "DATABASE_URL": (
                f"postgresql://{value('POSTGRES_USER')}:{value('POSTGRES_PASSWORD')}"
                f"@localhost:5432/{value('POSTGRES_DB')}"
            ),
        }


settings = Settings()
