"""
Regression tests for #34 (backend): AWS error -> HTTP status mapping, the
generation-counter items cache, and the removed per-call round-trips.

Integration tests use `requests` against API_URL (live stack); the LocalStack
outage cases can't stop the shared container mid-suite, so they drive the app
in-process through a minimal ASGI call with a stubbed boto3 client.
"""
import asyncio
import datetime
import json
import os
import uuid
from decimal import Decimal

import requests
from botocore.exceptions import (
    ClientError,
    ConnectTimeoutError,
    EndpointConnectionError,
    ParamValidationError,
    ReadTimeoutError,
)

from app.api.errors import status_for_botocore_error, status_for_client_error
from app.schemas.item import ItemCreate
from app.services import items as items_service
from app.services.aws import AWSService, get_aws_service

API_URL = os.getenv("API_URL", "http://localhost:8000")
TIMEOUT = 30


def _name(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _client_error(code: str, http_status: int = 400, operation: str = "Op") -> ClientError:
    return ClientError(
        {"Error": {"Code": code, "Message": "boom"}, "ResponseMetadata": {"HTTPStatusCode": http_status}},
        operation,
    )


# ------------------------------------------------------------------------------
# Status mapping (unit)
# ------------------------------------------------------------------------------


def test_client_error_codes_map_to_http_statuses():
    """Verify not-found/validation/conflict/throttling/other codes map to 404/400/409/429/502."""
    cases = {
        "ResourceNotFoundException": 404,
        "QueueDoesNotExist": 404,
        "AWS.SimpleQueueService.NonExistentQueue": 404,
        "NoSuchKey": 404,
        "ValidationException": 400,
        "InvalidParameterValueException": 400,
        "ResourceInUseException": 409,
        "ResourceConflictException": 409,
        "ThrottlingException": 429,
        "InternalFailure": 502,
        "SomethingUnexpected": 502,
    }
    for code, expected in cases.items():
        assert status_for_client_error(_client_error(code, http_status=500)) == expected, code


def test_unknown_client_error_with_http_404_is_not_found():
    """Verify an unlisted code whose HTTP status is 404 still maps to 404."""
    assert status_for_client_error(_client_error("SomeNewNotFound", http_status=404)) == 404


def test_botocore_connection_errors_map_to_503():
    """Verify connect/read timeouts and refused connections mean 'LocalStack unavailable'."""
    for exc in (
        EndpointConnectionError(endpoint_url="http://localstack:4566"),
        ConnectTimeoutError(endpoint_url="http://localstack:4566"),
        ReadTimeoutError(endpoint_url="http://localstack:4566"),
    ):
        status, detail = status_for_botocore_error(exc)
        assert status == 503, type(exc).__name__
        assert detail.startswith("LocalStack unavailable")


def test_botocore_param_validation_error_maps_to_400():
    """Verify a client-side parameter validation failure is a 400, not a 5xx."""
    status, _ = status_for_botocore_error(ParamValidationError(report="bad QueueName"))
    assert status == 400


# ------------------------------------------------------------------------------
# LocalStack down (in-process ASGI call with a stubbed boto3 client)
# ------------------------------------------------------------------------------


class _DownClient:
    """boto3 client stub whose every operation fails to connect."""

    def __getattr__(self, name):
        def _fail(*args, **kwargs):
            raise EndpointConnectionError(endpoint_url="http://localstack:4566")

        return _fail


def _asgi_get(app, path: str) -> tuple[int, dict]:
    """Performs a GET through the ASGI app without an HTTP client library."""

    async def run():
        messages = []
        sent = False

        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": b"", "more_body": False}
            return {"type": "http.disconnect"}

        async def send(message):
            messages.append(message)

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [(b"host", b"testserver")],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }
        await app(scope, receive, send)
        start = next(m for m in messages if m["type"] == "http.response.start")
        body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
        return start["status"], json.loads(body)

    return asyncio.run(run())


def test_list_endpoints_return_503_when_localstack_is_down():
    """Verify list endpoints report 503 instead of an empty list when LocalStack is unreachable."""
    from app.main import app

    service = AWSService()
    down = _DownClient()
    for attr in ("sqs", "dynamodb", "secretsmanager", "lambda_client", "events", "kinesis"):
        service.__dict__[attr] = down  # pre-fill the cached_property
    app.dependency_overrides[get_aws_service] = lambda: service
    try:
        for path in (
            "/aws/sqs/queues",
            "/aws/dynamodb/tables",
            "/aws/secrets",
            "/aws/lambda/functions",
            "/aws/events/buses",
            "/aws/kinesis/streams",
        ):
            status, body = _asgi_get(app, path)
            assert status == 503, (path, status, body)
            assert body["detail"].startswith("LocalStack unavailable"), body
    finally:
        app.dependency_overrides.pop(get_aws_service, None)


# ------------------------------------------------------------------------------
# Not-found errors against the live stack
# ------------------------------------------------------------------------------


def test_send_to_unknown_sqs_queue_returns_404():
    """Verify sending to a queue that does not exist is a 404, not a 400."""
    res = requests.post(
        f"{API_URL}/aws/sqs/messages",
        json={"queue_name": _name("missing-queue"), "message_body": "hi"},
        timeout=TIMEOUT,
    )
    assert res.status_code == 404, res.text
    assert "detail" in res.json()


def test_receive_from_unknown_sqs_queue_returns_404():
    """Verify receiving from a queue that does not exist is a 404."""
    res = requests.get(
        f"{API_URL}/aws/sqs/messages",
        params={"queue_name": _name("missing-queue")},
        timeout=TIMEOUT,
    )
    assert res.status_code == 404, res.text


def test_missing_secret_returns_404():
    """Verify a secret that does not exist is a 404 with a detail message."""
    res = requests.get(f"{API_URL}/aws/secrets/{_name('missing-secret')}", timeout=TIMEOUT)
    assert res.status_code == 404, res.text
    assert "detail" in res.json()


def test_scan_missing_dynamodb_table_returns_404():
    """Verify scanning a table that does not exist is a 404 (ResourceNotFoundException)."""
    res = requests.get(
        f"{API_URL}/aws/dynamodb/items",
        params={"table_name": _name("missing_table")},
        timeout=TIMEOUT,
    )
    assert res.status_code == 404, res.text


def test_invoke_unknown_lambda_returns_404():
    """Verify invoking a function that does not exist is a 404."""
    res = requests.post(
        f"{API_URL}/aws/lambda/invoke",
        json={"name": _name("missing-fn"), "payload": {}},
        timeout=60,
    )
    assert res.status_code == 404, res.text


def test_download_missing_s3_object_returns_404():
    """Verify downloading a key that does not exist is a 404."""
    res = requests.get(f"{API_URL}/s3/file", params={"key": _name("missing-object")}, timeout=TIMEOUT)
    assert res.status_code == 404, res.text


def test_sqs_queue_round_trip_still_works():
    """Verify create, send, receive and purge work on a real queue."""
    queue = _name("errors-queue")
    assert requests.post(f"{API_URL}/aws/sqs/queues", json={"name": queue}, timeout=TIMEOUT).status_code == 200
    sent = requests.post(
        f"{API_URL}/aws/sqs/messages",
        json={"queue_name": queue, "message_body": "payload"},
        timeout=TIMEOUT,
    )
    assert sent.status_code == 200, sent.text
    received = requests.get(f"{API_URL}/aws/sqs/messages", params={"queue_name": queue}, timeout=TIMEOUT)
    assert received.status_code == 200
    assert any(m["body"] == "payload" for m in received.json()["messages"])
    purged = requests.delete(f"{API_URL}/aws/sqs/queues", params={"queue_name": queue}, timeout=TIMEOUT)
    assert purged.status_code == 200, purged.text


# ------------------------------------------------------------------------------
# Items cache: generation counter instead of SCAN + DEL
# ------------------------------------------------------------------------------


class _MemoryRedis:
    """In-memory stand-in for the async Redis client that records calls."""

    def __init__(self):
        self.data: dict[str, str] = {}

    async def get(self, key):
        return self.data.get(key)

    async def setex(self, key, ttl, value):
        self.data[key] = value

    async def incr(self, key):
        self.data[key] = str(int(self.data.get(key, "0")) + 1)
        return int(self.data[key])

    def __getattr__(self, name):
        # scan_iter, delete, keys, ... must never be used by the items cache
        raise AssertionError(f"unexpected Redis call: {name}")


class _RowsConn:
    def __init__(self, rows):
        self.rows = rows

    async def fetchrow(self, *args):
        return self.rows[0]

    async def fetch(self, *args):
        return list(self.rows)


class _RowsAcquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


class _RowsPool:
    def __init__(self, rows):
        self.conn = _RowsConn(rows)

    def acquire(self):
        return _RowsAcquire(self.conn)


def _row(item_id: int, name: str) -> dict:
    return {
        "id": item_id,
        "name": name,
        "price": Decimal("1.50"),
        "is_offer": False,
        "created_at": datetime.datetime(2026, 1, 1),
    }


def test_create_item_bumps_generation_without_scanning():
    """Verify a create INCRs items:gen, never SCANs/DELs, and keeps item:{id} entries."""
    redis = _MemoryRedis()
    redis.data["item:1"] = json.dumps({"id": 1})
    pool = _RowsPool([_row(1, "first")])

    first = asyncio.run(items_service.get_items(pool, redis, limit=5))
    assert first["source"] == "database (PostgreSQL)"
    assert "items:gen:0:limit:5" in redis.data
    assert asyncio.run(items_service.get_items(pool, redis, limit=5))["source"] == "cache (Redis)"

    pool.conn.rows.insert(0, _row(2, "second"))
    asyncio.run(items_service.create_item(pool.conn, redis, ItemCreate(name="second", price=1.5)))

    assert redis.data[items_service.ITEMS_GEN_KEY] == "1"
    assert "item:1" in redis.data  # per-item entries survive a create
    after = asyncio.run(items_service.get_items(pool, redis, limit=5))
    assert after["source"] == "database (PostgreSQL)"
    assert [it["name"] for it in after["items"]] == ["second", "first"]


def test_created_item_shows_up_in_cached_list():
    """Verify GET /items reflects a new item even when the list was just cached."""
    params = {"limit": 100}
    requests.get(f"{API_URL}/items", params=params, timeout=TIMEOUT)
    cached = requests.get(f"{API_URL}/items", params=params, timeout=TIMEOUT)
    assert cached.status_code == 200

    name = _name("gen-cache-item")
    created = requests.post(f"{API_URL}/items", json={"name": name, "price": 2.5}, timeout=TIMEOUT)
    assert created.status_code == 201, created.text

    after = requests.get(f"{API_URL}/items", params=params, timeout=TIMEOUT)
    assert after.status_code == 200
    assert name in [it["name"] for it in after.json()["items"]]
