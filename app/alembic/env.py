import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None

# The app (asyncpg) and Alembic (SQLAlchemy + psycopg 3) share one
# DATABASE_URL. asyncpg only accepts the plain postgresql:// / postgres://
# scheme, so the explicit SQLAlchemy driver is chosen here instead of in the
# env var.
_SQLALCHEMY_SCHEME = "postgresql+psycopg://"
_KNOWN_SCHEMES = (
    "postgresql+asyncpg://",
    "postgresql+psycopg2://",
    "postgresql+psycopg://",
    "postgresql://",
    "postgres://",
)


def get_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Alembic reads the database URL from the "
            "environment, e.g. DATABASE_URL=postgresql://user:pass@host:5432/db"
        )
    for scheme in _KNOWN_SCHEMES:
        if url.startswith(scheme):
            return _SQLALCHEMY_SCHEME + url[len(scheme):]
    raise RuntimeError(
        "DATABASE_URL must be a PostgreSQL URL (postgresql://...), got scheme "
        f"{url.split('://', 1)[0]!r}"
    )


def run_migrations_offline() -> None:
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # The URL is passed straight to create_engine rather than through
    # config.set_main_option, whose ConfigParser interpolation would choke on
    # '%' in a percent-encoded password.
    connectable = create_engine(get_database_url(), poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
