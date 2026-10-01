"""
Shared fixtures for the integration tests (live stack at API_URL).

Nothing here is autouse: unit tests in the same pytest run never touch
API_URL or the stack unless they request one of these fixtures.
"""
import os
import time
import uuid
import warnings
from collections.abc import Callable

import pytest
import requests

API_URL = os.getenv("API_URL", "http://localhost:8000")

# Default per-request timeout: a hung service fails the test instead of CI.
DEFAULT_TIMEOUT = 30
# Lambda deploys wait (bounded) for the function to become Active/Updated,
# so they can take longer than a plain request on a cold LocalStack.
LAMBDA_DEPLOY_TIMEOUT = 60
LAMBDA_INVOKE_TIMEOUT = 30


def unique_name(prefix: str) -> str:
    """Returns prefix plus a random suffix, so reruns never hit existing resources."""
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


class ApiClient:
    """Thin requests wrapper: prefixes API_URL and always sets a timeout.

    Uses a fresh connection per call (no Session), so a keep-alive socket
    the server already closed can't fail a request between slow steps.
    """

    def __init__(self, base_url: str, timeout: float):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request(self, method: str, path: str, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", self.timeout)
        return requests.request(method, f"{self.base_url}{path}", **kwargs)

    def get(self, path: str, **kwargs) -> requests.Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs) -> requests.Response:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs) -> requests.Response:
        return self.request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs) -> requests.Response:
        return self.request("DELETE", path, **kwargs)


@pytest.fixture(scope="session")
def api() -> ApiClient:
    """Client for the live API at API_URL with a default timeout."""
    return ApiClient(API_URL, DEFAULT_TIMEOUT)


@pytest.fixture
def cleanup():
    """Registers teardown callables, run in reverse order after the test.

    Cleanup is best-effort: a failing call only warns, so it never hides
    (or replaces) the test's own failure.
    """
    calls: list[Callable[[], object]] = []
    yield calls.append
    for call in reversed(calls):
        try:
            call()
        except Exception as e:  # teardown must never raise
            warnings.warn(f"integration test cleanup failed: {e!r}", stacklevel=1)


@pytest.fixture
def queue_name(api, cleanup) -> str:
    """Unique SQS queue name; purged on teardown (the API has no queue delete)."""
    name = unique_name("pytest-queue")
    cleanup(lambda: api.delete("/aws/sqs/queues", params={"queue_name": name}))
    return name


@pytest.fixture
def table_name(api, cleanup) -> str:
    """Unique DynamoDB table name; the table is deleted on teardown."""
    name = unique_name("pytest_table")
    cleanup(lambda: api.delete("/aws/dynamodb/tables", params={"table_name": name}))
    return name


@pytest.fixture
def stream_name(api, cleanup) -> str:
    """Unique Kinesis stream name; the stream is deleted on teardown."""
    name = unique_name("pytest-stream")
    cleanup(lambda: api.delete("/aws/kinesis/streams", params={"name": name}))
    return name


@pytest.fixture
def function_name(api, cleanup) -> str:
    """Unique Lambda function name; the function is deleted on teardown."""
    name = unique_name("pytest_fn")
    cleanup(lambda: api.delete("/aws/lambda/functions", params={"name": name}))
    return name


@pytest.fixture
def s3_key(api, cleanup) -> Callable[[str], str]:
    """Factory for unique S3 keys ending in the given name; each is deleted on teardown."""

    def make(name: str = "object.txt") -> str:
        key = f"pytest-{uuid.uuid4().hex[:10]}-{name}"
        cleanup(lambda: api.delete("/s3/file", params={"key": key}))
        return key

    return make


@pytest.fixture
def secret_name() -> str:
    """Unique secret name. The API has no secret delete, so it is left behind."""
    return unique_name("pytest-secret")


@pytest.fixture
def deploy_lambda(api) -> Callable[[str, str], requests.Response]:
    """Deploys (creates or updates) a Python Lambda function."""

    def deploy(name: str, code: str) -> requests.Response:
        return api.post(
            "/aws/lambda/functions", json={"name": name, "code": code}, timeout=LAMBDA_DEPLOY_TIMEOUT
        )

    return deploy


@pytest.fixture
def invoke_lambda(api) -> Callable[[str, object], requests.Response]:
    """Invokes a function, retrying briefly while LocalStack cold-starts it."""

    def invoke(name: str, payload: object) -> requests.Response:
        for attempt in range(5):
            res = api.post(
                "/aws/lambda/invoke", json={"name": name, "payload": payload}, timeout=LAMBDA_INVOKE_TIMEOUT
            )
            if res.status_code == 200 or attempt == 4:
                break
            time.sleep(2)
        return res

    return invoke
