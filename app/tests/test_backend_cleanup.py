"""
Regression tests for #35 (backend cleanup): paginated AWS listings and
Kinesis reads across shards.

Unit tests drive real boto3 clients through botocore's Stubber, so the
actual request parameters (MaxResults, NextToken, ContinuationToken, ...)
are checked without needing LocalStack. Integration tests use `requests`
against API_URL (live stack).
"""
import asyncio
import datetime
import os
import time
import uuid

import requests
from botocore.stub import ANY, Stubber
from fastapi import APIRouter, FastAPI
from prometheus_client import REGISTRY

from app.core.metrics import PrometheusMetricsMiddleware
from app.services.aws import AWSService
from app.services.s3 import S3Service

API_URL = os.getenv("API_URL", "http://localhost:8000")
TIMEOUT = 30
NOW = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)


def _name(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


# ------------------------------------------------------------------------------
# Pagination (unit, stubbed boto3 clients)
# ------------------------------------------------------------------------------


def test_list_sqs_queues_follows_next_token():
    """Verify every ListQueues page is read, not just the first."""
    service = AWSService()
    urls = [f"http://localstack:4566/000000000000/q-{i}" for i in range(3)]
    with Stubber(service.sqs) as stub:
        stub.add_response("list_queues", {"QueueUrls": urls[:2], "NextToken": "t1"}, {})
        stub.add_response("list_queues", {"QueueUrls": urls[2:]}, {"NextToken": "t1"})
        for _ in urls:
            stub.add_response("get_queue_attributes", {"Attributes": {}}, {"QueueUrl": ANY, "AttributeNames": ANY})
        queues = service.list_sqs_queues()
        stub.assert_no_pending_responses()
    assert [q["name"] for q in queues] == ["q-0", "q-1", "q-2"]


def test_list_dynamodb_tables_follows_last_evaluated_table_name():
    """Verify ListTables pages are followed via ExclusiveStartTableName."""
    service = AWSService()
    with Stubber(service.dynamodb) as stub:
        stub.add_response("list_tables", {"TableNames": ["tbl-a", "tbl-b"], "LastEvaluatedTableName": "tbl-b"}, {})
        stub.add_response("list_tables", {"TableNames": ["tbl-c"]}, {"ExclusiveStartTableName": "tbl-b"})
        for name in ("tbl-a", "tbl-b", "tbl-c"):
            stub.add_response(
                "describe_table",
                {"Table": {"TableName": name, "ItemCount": 0, "TableStatus": "ACTIVE",
                           "KeySchema": [{"AttributeName": "id", "KeyType": "HASH"}]}},
                {"TableName": name},
            )
        tables = service.list_dynamodb_tables()
        stub.assert_no_pending_responses()
    assert [t["name"] for t in tables] == ["tbl-a", "tbl-b", "tbl-c"]


def test_list_lambda_functions_follows_next_marker():
    """Verify ListFunctions pages (50 functions each) are followed via Marker."""
    service = AWSService()
    page1 = [{"FunctionName": f"fn-{i}"} for i in range(50)]
    with Stubber(service.lambda_client) as stub:
        stub.add_response("list_functions", {"Functions": page1, "NextMarker": "m1"}, {})
        stub.add_response("list_functions", {"Functions": [{"FunctionName": "fn-50"}]}, {"Marker": "m1"})
        functions = service.list_lambda_functions()
        stub.assert_no_pending_responses()
    assert len(functions) == 51
    assert functions[-1]["name"] == "fn-50"


def test_list_secrets_follows_next_token():
    """Verify ListSecrets pages are followed via NextToken."""
    service = AWSService()
    with Stubber(service.secretsmanager) as stub:
        stub.add_response("list_secrets", {"SecretList": [{"Name": "s1", "LastChangedDate": NOW}], "NextToken": "t1"}, {})
        stub.add_response("list_secrets", {"SecretList": [{"Name": "s2"}]}, {"NextToken": "t1"})
        secrets = service.list_secrets()
        stub.assert_no_pending_responses()
    assert [s["name"] for s in secrets] == ["s1", "s2"]
    assert secrets[0]["last_changed"] == NOW.isoformat()


def test_list_bucket_objects_follows_continuation_token():
    """Verify more than 1000 S3 objects are listed by following ContinuationToken."""
    service = S3Service(bucket_name="test-bucket")
    service._bucket_ready = True  # skip CreateBucket
    page1 = [{"Key": f"k{i:04d}", "Size": 1, "LastModified": NOW} for i in range(1000)]
    with Stubber(service.client) as stub:
        stub.add_response(
            "list_objects_v2",
            {"Contents": page1, "IsTruncated": True, "NextContinuationToken": "c1"},
            {"Bucket": "test-bucket"},
        )
        stub.add_response(
            "list_objects_v2",
            {"Contents": [{"Key": "k1000", "Size": 1, "LastModified": NOW}], "IsTruncated": False},
            {"Bucket": "test-bucket", "ContinuationToken": "c1"},
        )
        listing = service.list_bucket_objects()
        stub.assert_no_pending_responses()
    assert listing["count"] == 1001
    assert listing["objects"][-1]["key"] == "k1000"


# ------------------------------------------------------------------------------
# Kinesis: every shard is read (unit, stubbed; and live)
# ------------------------------------------------------------------------------

SHARD_ITERATOR = "iterator-0123456789"


def _stream_description(*shard_ids: str) -> dict:
    return {
        "StreamDescription": {
            "StreamName": "s",
            "StreamARN": "arn:aws:kinesis:us-east-1:000000000000:stream/s",
            "StreamStatus": "ACTIVE",
            "Shards": [
                {
                    "ShardId": shard_id,
                    "HashKeyRange": {"StartingHashKey": "0", "EndingHashKey": "1"},
                    "SequenceNumberRange": {"StartingSequenceNumber": "1"},
                }
                for shard_id in shard_ids
            ],
            "HasMoreShards": False,
            "RetentionPeriodHours": 24,
            "StreamCreationTimestamp": NOW,
            "EnhancedMonitoring": [],
        }
    }


def _record(seq: str, data: str, arrival: datetime.datetime) -> dict:
    return {"SequenceNumber": seq, "PartitionKey": "pk", "Data": data.encode(), "ApproximateArrivalTimestamp": arrival}


def _expect_iterator(stub: Stubber, shard_id: str) -> None:
    stub.add_response(
        "get_shard_iterator",
        {"ShardIterator": SHARD_ITERATOR},
        {"StreamName": "s", "ShardId": shard_id, "ShardIteratorType": "TRIM_HORIZON"},
    )


def _expect_records(stub: Stubber, limit: int, records: list, behind: int = 0, more: bool = True) -> None:
    response = {"Records": records, "MillisBehindLatest": behind}
    if more:
        response["NextShardIterator"] = SHARD_ITERATOR
    stub.add_response("get_records", response, {"ShardIterator": SHARD_ITERATOR, "Limit": limit})


def test_kinesis_read_covers_every_shard_and_follows_next_shard_iterator():
    """Verify records come from all shards, following NextShardIterator past an empty batch."""
    service = AWSService()
    later = NOW + datetime.timedelta(seconds=1)
    with Stubber(service.kinesis) as stub:
        stub.add_response("describe_stream", _stream_description("shard-0", "shard-1"), {"StreamName": "s"})
        # shard-0: an empty batch while still behind, then its record, then caught up
        _expect_iterator(stub, "shard-0")
        _expect_records(stub, 10, [], behind=500)
        _expect_records(stub, 10, [_record("1", "zero", later)])
        _expect_records(stub, 9, [])
        # shard-1: one older record, then the shard is closed (no next iterator)
        _expect_iterator(stub, "shard-1")
        _expect_records(stub, 10, [_record("2", "one", NOW)])
        _expect_records(stub, 9, [], more=False)
        records = service.get_kinesis_records("s", limit=10)
        stub.assert_no_pending_responses()
    # Merged across shards by arrival time
    assert [r["data"] for r in records] == ["one", "zero"]


def test_kinesis_read_is_bounded_by_limit():
    """Verify at most `limit` records are read per shard and returned in total."""
    service = AWSService()
    with Stubber(service.kinesis) as stub:
        stub.add_response("describe_stream", _stream_description("shard-0", "shard-1"), {"StreamName": "s"})
        for shard_id in ("shard-0", "shard-1"):
            _expect_iterator(stub, shard_id)
            _expect_records(stub, 2, [_record(f"{shard_id}-{i}", f"{shard_id}-{i}", NOW) for i in range(2)])
        records = service.get_kinesis_records("s", limit=2)
        stub.assert_no_pending_responses()
    assert [r["data"] for r in records] == ["shard-0-0", "shard-0-1"]


def test_kinesis_records_from_every_shard_via_api():
    """Verify GET /aws/kinesis/records returns records written to each shard of a 2-shard stream."""
    stream = _name("test-pytest-kinesis")
    res = requests.post(
        f"{API_URL}/aws/kinesis/streams", json={"stream_name": stream, "shard_count": 2}, timeout=TIMEOUT
    )
    assert res.status_code == 200, res.text
    try:
        # A 2-shard stream can take a few seconds to become ACTIVE in
        # LocalStack; putting records earlier can stall.
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            streams = requests.get(f"{API_URL}/aws/kinesis/streams", timeout=TIMEOUT).json()["streams"]
            if any(s["name"] == stream and s["status"] == "ACTIVE" for s in streams):
                break
            time.sleep(1)
        written = {}  # shard id -> first data written to it
        for i in range(40):
            res = requests.post(
                f"{API_URL}/aws/kinesis/records",
                json={"stream_name": stream, "partition_key": f"pk-{i}", "data": f"rec-{i}"},
                timeout=60,
            )
            assert res.status_code == 200, res.text
            written.setdefault(res.json()["shard_id"], f"rec-{i}")
            if len(written) == 2:
                break
        assert len(written) == 2, "partition keys never hashed to both shards"
        res = requests.get(
            f"{API_URL}/aws/kinesis/records", params={"stream_name": stream, "limit": 50}, timeout=TIMEOUT
        )
        assert res.status_code == 200, res.text
        data = {r["data"] for r in res.json()["records"]}
        assert set(written.values()) <= data, (written, data)
    finally:
        requests.delete(f"{API_URL}/aws/kinesis/streams", params={"name": stream}, timeout=TIMEOUT)


# ------------------------------------------------------------------------------
# Metrics middleware (in-process ASGI)
# ------------------------------------------------------------------------------


def _asgi_request(app, path: str) -> int:
    """Performs a GET through an ASGI app and returns the response status."""

    async def run():
        status = None

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]

        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET",
            "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": b"",
            "root_path": "", "headers": [(b"host", b"testserver")],
            "client": ("127.0.0.1", 12345), "server": ("testserver", 80),
        }
        try:
            await app(scope, receive, send)
        except RuntimeError:
            pass  # re-raised by ServerErrorMiddleware after sending the 500
        return status

    return asyncio.run(run())


def _count(endpoint: str, status: str) -> float:
    value = REGISTRY.get_sample_value("http_requests_total", {"method": "GET", "endpoint": endpoint, "status": status})
    return value or 0.0


def test_metrics_middleware_labels_route_template_and_status():
    """Verify the ASGI metrics middleware records route templates, statuses and failures."""
    app = FastAPI()
    app.add_middleware(PrometheusMetricsMiddleware)
    router = APIRouter()

    @router.get("/{thing_id}", status_code=201)
    def get_thing(thing_id: int):
        return {"id": thing_id}

    @router.get("/boom/now")
    def boom():
        raise RuntimeError("boom")

    app.include_router(router, prefix="/things-35")

    before_ok = _count("/things-35/{thing_id}", "201")
    before_err = _count("/things-35/boom/now", "500")
    before_latency = REGISTRY.get_sample_value(
        "http_request_duration_seconds_count", {"endpoint": "/things-35/{thing_id}"}
    ) or 0.0

    assert _asgi_request(app, "/things-35/1") == 201
    assert _asgi_request(app, "/things-35/2") == 201
    assert _asgi_request(app, "/things-35/boom/now") == 500

    assert _count("/things-35/{thing_id}", "201") == before_ok + 2
    assert _count("/things-35/boom/now", "500") == before_err + 1
    latency = REGISTRY.get_sample_value("http_request_duration_seconds_count", {"endpoint": "/things-35/{thing_id}"})
    assert latency == before_latency + 2
