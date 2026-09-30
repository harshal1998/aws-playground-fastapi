# Dockerfile
# Stages:
#   base    - Python 3.11 + the runtime lock (requirements.txt)
#   test    - base + dev/test tooling (requirements-dev.txt); used by the
#             compose `test` service and CI, never published
#   runtime - the published API image (default target, so it must stay last)
FROM python:3.11-slim AS base

# Set the working directory to /app
WORKDIR /app

# copy only the runtime lock file used to install dependencies
COPY requirements.txt .

# install the locked runtime dependencies
RUN pip install --no-cache-dir -r requirements.txt

# ------------------------------------------------------------------------------
FROM base AS test

COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY . .

CMD ["pytest", "-v", "app/tests/"]

# ------------------------------------------------------------------------------
FROM base AS runtime

# copy the rest of the files
COPY . .

# Inform Docker that the container is listening on port 8000
EXPOSE 8000

# command to run on container start
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
