# Dockerfile
# Stages:
#   base    - Python 3.11 + the runtime lock (requirements.txt), non-root user
#   test    - base + dev/test tooling (requirements-dev.txt); used by the
#             compose `test` service and CI, never published
#   runtime - the published API image (default target, so it must stay last)
FROM python:3.11-slim AS base

# Unbuffered stdout/stderr so log lines reach `docker logs` immediately;
# no .pyc files (the source is often bind-mounted read-only for this user).
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set the working directory to /app
WORKDIR /app

# Unprivileged user the app runs as. The source stays root-owned (read-only
# for the app); the only writable path it needs is the Prometheus
# multiprocess dir under /tmp, which is world-writable.
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app --no-create-home app

# copy only the runtime lock file used to install dependencies
COPY requirements.txt .

# install the locked runtime dependencies
RUN pip install -r requirements.txt

# ------------------------------------------------------------------------------
FROM base AS test

COPY requirements-dev.txt .
RUN pip install -r requirements-dev.txt

COPY . .

USER app

CMD ["pytest", "-v", "-p", "no:cacheprovider", "app/tests/"]

# ------------------------------------------------------------------------------
FROM base AS runtime

# copy the rest of the files
COPY . .

USER app

# Inform Docker that the container is listening on port 8000
EXPOSE 8000

# Apply database migrations, then replace the shell with uvicorn so it gets
# signals directly. Needs DATABASE_URL (see docs/environment-variables.md).
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
