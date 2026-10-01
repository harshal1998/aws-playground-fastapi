"""Shared fixtures for the unit tests.

Nothing here talks to a real service: Redis is fakeredis, PostgreSQL is an
in-memory stub of the asyncpg calls the items service makes, and AWS is
moto's in-process backend.
"""
import datetime
from decimal import Decimal

import pytest
from moto import mock_aws

from app.services.aws import AWSService
from app.services.s3 import S3Service

REGION = "us-east-1"
BUCKET = "unit-test-bucket"

# botocore reads these from the environment when a client is created with
# endpoint_url=None; moto only intercepts requests to real AWS URLs, so one
# pointing at LocalStack would escape the mock.
_ENDPOINT_ENV_VARS = ("AWS_ENDPOINT_URL", "AWS_ENDPOINT_URL_S3", "AWS_PROFILE", "AWS_DEFAULT_PROFILE")


# ------------------------------------------------------------------------------
# PostgreSQL: in-memory stand-in for the asyncpg pool/connection
# ------------------------------------------------------------------------------
class FakeItemsDB:
    """Stateful stub of the items table, answering the items service's queries.

    Unlike the fixed-row StubPool in test_s3_and_cache.py, writes are kept,
    so cache invalidation after a create can be observed. Query counts show
    whether a read was served by Redis or by the database.
    """

    def __init__(self):
        self.rows: list[dict] = []
        self.fetch_calls = 0
        self.fetchrow_calls = 0

    def add(self, name: str, price: str, is_offer: bool = False) -> dict:
        row = {
            "id": len(self.rows) + 1,
            "name": name,
            "price": Decimal(price),
            "is_offer": is_offer,
            "created_at": datetime.datetime(2026, 1, 1, 12, 0, len(self.rows) % 60),
        }
        self.rows.append(row)
        return row

    # asyncpg.Connection API used by app/services/items.py
    async def fetchrow(self, query: str, *args):
        self.fetchrow_calls += 1
        if query.lstrip().upper().startswith("INSERT"):
            name, price, is_offer = args
            return self.add(name, str(price), is_offer)
        (item_id,) = args
        return next((r for r in self.rows if r["id"] == item_id), None)

    async def fetch(self, query: str, limit: int):
        self.fetch_calls += 1
        return sorted(self.rows, key=lambda r: r["id"], reverse=True)[:limit]

    # asyncpg.Pool API: `async with pool.acquire() as conn`
    def acquire(self):
        db = self

        class _Acquire:
            async def __aenter__(self):
                return db

            async def __aexit__(self, *exc):
                return False

        return _Acquire()


@pytest.fixture
def db() -> FakeItemsDB:
    return FakeItemsDB()


# ------------------------------------------------------------------------------
# AWS: moto
# ------------------------------------------------------------------------------
@pytest.fixture
def mocked_aws(monkeypatch):
    """Activates moto with dummy credentials and no endpoint overrides."""
    for name in _ENDPOINT_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_IGNORE_CONFIGURED_ENDPOINT_URLS", "true")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    # LocalStack's account, which AWSService's Lambda role ARN hard-codes.
    monkeypatch.setenv("MOTO_ACCOUNT_ID", "000000000000")
    with mock_aws():
        yield


def _moto_kwargs() -> dict:
    # endpoint_url=None: the services default to settings.AWS_ENDPOINT_URL
    # (LocalStack), which moto would not intercept.
    return {
        "endpoint_url": None,
        "region_name": REGION,
        "aws_access_key_id": "testing",
        "aws_secret_access_key": "testing",
    }


@pytest.fixture
def aws_service(mocked_aws) -> AWSService:
    return AWSService(**_moto_kwargs())


@pytest.fixture
def s3_service(mocked_aws) -> S3Service:
    return S3Service(bucket_name=BUCKET, **_moto_kwargs())
