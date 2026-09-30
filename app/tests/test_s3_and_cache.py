import asyncio
import datetime
import http.client
import os
from decimal import Decimal
from urllib.parse import quote, urlsplit

import redis.asyncio as aioredis
import requests

from app.core.config import settings
from app.schemas.item import ItemCreate
from app.services import items as items_service

API_URL = os.getenv("API_URL", "http://localhost:8000")

# ------------------------------------------------------------------------------
# Redis outage: the items cache must be best-effort
# ------------------------------------------------------------------------------
# Stopping the shared redis container mid-suite would break the other tests,
# so these drive the service layer directly with a Redis client that fails
# every call, and a stub PostgreSQL connection.

ROW = {
    "id": 1,
    "name": "Cache Outage Item",
    "price": Decimal("9.99"),
    "is_offer": False,
    "created_at": datetime.datetime(2026, 1, 1),
}


class FailingRedis:
    """Redis client stub whose every call raises a connection error."""

    def _fail(self, *args, **kwargs):
        raise aioredis.ConnectionError("Error connecting to redis:6379. Connection refused.")

    async def get(self, *args, **kwargs):
        self._fail()

    async def setex(self, *args, **kwargs):
        self._fail()

    async def delete(self, *args, **kwargs):
        self._fail()

    async def scan_iter(self, *args, **kwargs):
        self._fail()
        yield  # pragma: no cover - makes this an async generator


class StubConn:
    async def fetchrow(self, *args):
        return ROW

    async def fetch(self, *args):
        return [ROW]


class StubAcquire:
    async def __aenter__(self):
        return StubConn()

    async def __aexit__(self, *exc):
        return False


class StubPool:
    def acquire(self):
        return StubAcquire()


def test_get_items_falls_back_to_postgres_when_redis_fails():
    """Verify listing items serves from PostgreSQL when Redis raises."""
    result = asyncio.run(items_service.get_items(StubPool(), FailingRedis(), limit=5))
    assert result["source"] == "database (PostgreSQL)"
    assert result["count"] == 1
    assert result["items"][0]["name"] == ROW["name"]


def test_get_item_by_id_falls_back_to_postgres_when_redis_fails():
    """Verify reading one item serves from PostgreSQL when Redis raises."""
    result = asyncio.run(items_service.get_item_by_id(StubPool(), FailingRedis(), 1))
    assert result["id"] == 1
    assert result["price"] == 9.99


def test_create_item_succeeds_when_cache_invalidation_fails():
    """Verify a failed cache invalidation does not fail item creation."""
    item = ItemCreate(name=ROW["name"], price=9.99, is_offer=False)
    result = asyncio.run(items_service.create_item(StubConn(), FailingRedis(), item))
    assert result["id"] == 1
    assert result["name"] == ROW["name"]


# ------------------------------------------------------------------------------
# S3 downloads: served as attachments, never rendered inline
# ------------------------------------------------------------------------------


def _upload(key: str, content: bytes, content_type: str = "application/octet-stream") -> requests.Response:
    return requests.post(
        f"{API_URL}/s3/upload",
        params={"filename": key},
        data=content,
        headers={"Content-Type": content_type},
        timeout=10,
    )


def _delete(key: str) -> None:
    requests.delete(f"{API_URL}/s3/file", params={"key": key}, timeout=10)


def test_s3_download_is_attachment_with_nosniff():
    """Verify an uploaded HTML file is downloaded, not rendered on the portal origin."""
    key = "regression_xss.html"
    assert _upload(key, b"<script>alert(1)</script>", "text/html").status_code == 200
    try:
        response = requests.get(f"{API_URL}/s3/file", params={"key": key}, timeout=10)
        assert response.status_code == 200
        assert response.headers["Content-Disposition"].startswith("attachment;")
        assert 'filename="regression_xss.html"' in response.headers["Content-Disposition"]
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.content == b"<script>alert(1)</script>"
    finally:
        _delete(key)


def test_s3_download_key_with_quotes_and_unicode():
    """Verify keys with quotes or non-Latin-1 characters get a valid header instead of a 500."""
    for key in ('résumé "v2".txt', "файл.txt"):
        assert _upload(key, b"hello").status_code == 200
        try:
            response = requests.get(f"{API_URL}/s3/file", params={"key": key}, timeout=10)
            assert response.status_code == 200
            disposition = response.headers["Content-Disposition"]
            assert disposition.startswith("attachment;")
            assert f"filename*=UTF-8''{quote(key, safe='')}" in disposition
            # The ASCII fallback must not contain a raw quote that ends it early.
            fallback = disposition.split('filename="', 1)[1].split('"', 1)[0]
            assert fallback.isascii()
            assert fallback.endswith(".txt")
            assert response.content == b"hello"
        finally:
            _delete(key)


# ------------------------------------------------------------------------------
# S3 uploads: size limit
# ------------------------------------------------------------------------------


def test_s3_upload_larger_than_nginx_default_succeeds():
    """Verify an upload over 1 MB (nginx's old default) but under the limit is stored intact."""
    key = "regression_2mb.bin"
    content = os.urandom(2 * 1024 * 1024)
    response = _upload(key, content)
    try:
        assert response.status_code == 200
        assert response.json()["size_bytes"] == len(content)
        download = requests.get(f"{API_URL}/s3/file", params={"key": key}, timeout=10)
        assert download.status_code == 200
        assert download.content == content
    finally:
        _delete(key)


def test_s3_upload_over_limit_returns_413():
    """Verify an upload declaring more than S3_MAX_UPLOAD_BYTES is rejected with 413."""
    # Send only the headers: the API must reject on the declared Content-Length
    # without reading the body. (Streaming an oversize body with requests would
    # race against the server closing the connection.)
    parsed = urlsplit(API_URL)
    conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=10)
    try:
        conn.putrequest("POST", "/s3/upload?filename=regression_too_large.bin")
        conn.putheader("Content-Type", "application/octet-stream")
        conn.putheader("Content-Length", str(settings.S3_MAX_UPLOAD_BYTES + 1))
        conn.endheaders()
        response = conn.getresponse()
        assert response.status == 413
    finally:
        conn.close()

    listing = requests.get(f"{API_URL}/s3/objects", timeout=10).json()
    assert "regression_too_large.bin" not in [obj["key"] for obj in listing["objects"]]
