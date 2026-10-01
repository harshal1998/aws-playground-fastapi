"""
Integration tests against the live stack at API_URL.

Every request has a timeout (via the `api` fixture), every AWS/S3 resource
gets a unique name per run and is removed in fixture teardown, and no test
assumes the items table starts empty, so the suite can be rerun against the
same stack.
"""
import time

from app.tests.conftest import unique_name

# ------------------------------------------------------------------------------
# Root / metrics
# ------------------------------------------------------------------------------


def test_root_endpoint(api):
    """Verify the root health check endpoint returns 200 and expected payload."""
    response = api.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "container_id" in data


def test_prometheus_metrics(api):
    """Verify that the Prometheus /metrics endpoint is exposed and functioning."""
    response = api.get("/metrics")
    assert response.status_code == 200
    assert (
        "http_requests_total" in response.text
        or "python_gc_objects_collected_total" in response.text
    )


# ------------------------------------------------------------------------------
# Items (PostgreSQL + Redis cache)
# ------------------------------------------------------------------------------


def test_create_and_read_item(api):
    """Verify creating an item in DB and retrieving it."""
    payload = {"name": unique_name("Integration Keyboard"), "price": 89.99, "is_offer": True}
    create_res = api.post("/items", json=payload)
    assert create_res.status_code == 201, create_res.text
    created_data = create_res.json()
    assert created_data["status"] == "created"
    item = created_data["item"]
    assert item["name"] == payload["name"]
    assert item["price"] == payload["price"]
    assert item["is_offer"] is True
    item_id = item["id"]

    get_res = api.get(f"/items/{item_id}")
    assert get_res.status_code == 200
    single_item = get_res.json()
    assert single_item["id"] == item_id
    assert single_item["name"] == payload["name"]


def test_create_item_rejects_non_positive_price(api):
    """Verify creating an item with a zero or negative price returns 422."""
    for bad_price in (0, -10.5):
        payload = {"name": "Invalid Price Item", "price": bad_price, "is_offer": False}
        response = api.post("/items", json=payload)
        assert response.status_code == 422, bad_price


def test_get_items_list(api):
    """Verify the items listing endpoint returns a valid list."""
    response = api.get("/items", params={"limit": 5})
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["items"], list)
    assert data["count"] == len(data["items"])
    assert len(data["items"]) <= 5


def test_redis_cache_behavior(api):
    """Verify that repeating a query hits the Redis cache."""
    res1 = api.get("/items", params={"limit": 3})
    assert res1.status_code == 200

    res2 = api.get("/items", params={"limit": 3})
    assert res2.status_code == 200
    assert res2.json()["source"] == "cache (Redis)"
    assert res2.json()["items"] == res1.json()["items"]


def test_item_create_invalidates_cached_list(api):
    """Verify a create makes the cached list stale: the next read comes from PostgreSQL and shows the item."""
    params = {"limit": 100}
    api.get("/items", params=params)  # populate the cache for this generation
    cached = api.get("/items", params=params)
    assert cached.status_code == 200
    assert cached.json()["source"] == "cache (Redis)"

    name = unique_name("cache-invalidation-item")
    created = api.post("/items", json={"name": name, "price": 3.25})
    assert created.status_code == 201, created.text
    item_id = created.json()["item"]["id"]

    after = api.get("/items", params=params)
    assert after.status_code == 200
    assert after.json()["source"] == "database (PostgreSQL)"
    # Newest first, so the new item is in the first page whatever the table holds.
    assert after.json()["items"][0]["id"] == item_id
    assert after.json()["items"][0]["name"] == name

    again = api.get("/items", params=params)
    assert again.json()["source"] == "cache (Redis)"
    assert again.json()["items"][0]["id"] == item_id


def test_item_not_found(api):
    """Verify requesting a non-existent item ID returns 404."""
    response = api.get("/items/2147483647")
    assert response.status_code == 404
    assert response.json()["detail"] == "Item not found"


# ------------------------------------------------------------------------------
# S3
# ------------------------------------------------------------------------------


def test_s3_upload_sample_and_list(api, s3_key):
    """Verify uploading the sample document to LocalStack S3 and seeing it in the listing."""
    key = s3_key("sample.txt")
    response = api.post("/s3/upload-sample", params={"filename": key})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "success"
    assert data["bucket"] == "fastapi-bucket"
    assert data["key"] == key

    listing = api.get("/s3/objects")
    assert listing.status_code == 200
    assert listing.json()["bucket"] == "fastapi-bucket"
    assert key in [obj["key"] for obj in listing.json()["objects"]]


def test_s3_download_and_delete_round_trip(api, s3_key):
    """Verify an uploaded object downloads intact, then is gone (404) after delete."""
    key = s3_key("round-trip.txt")
    content = f"round trip {key}".encode()
    upload = api.post(
        "/s3/upload", params={"filename": key}, data=content, headers={"Content-Type": "text/plain"}
    )
    assert upload.status_code == 200, upload.text

    download = api.get("/s3/file", params={"key": key})
    assert download.status_code == 200
    assert download.content == content
    assert download.headers["Content-Type"].startswith("text/plain")

    deleted = api.delete("/s3/file", params={"key": key})
    assert deleted.status_code == 200, deleted.text
    assert deleted.json() == {"status": "deleted", "key": key}

    assert api.get("/s3/file", params={"key": key}).status_code == 404
    listing = api.get("/s3/objects").json()
    assert key not in [obj["key"] for obj in listing["objects"]]


# ------------------------------------------------------------------------------
# AWS services (LocalStack)
# ------------------------------------------------------------------------------


def test_aws_status(api):
    """Verify LocalStack AWS health status endpoint."""
    response = api.get("/aws/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "s3" in data["active_services"]


def test_aws_sqs_lifecycle(api, queue_name):
    """Verify creating an SQS queue and sending/receiving a message."""
    q_res = api.post("/aws/sqs/queues", json={"name": queue_name})
    assert q_res.status_code == 200, q_res.text

    listed = api.get("/aws/sqs/queues")
    assert listed.status_code == 200
    assert queue_name in [q["name"] for q in listed.json()["queues"]]

    send_res = api.post("/aws/sqs/messages", json={"queue_name": queue_name, "message_body": "hello pytest"})
    assert send_res.status_code == 200, send_res.text

    # Each receive long-polls for 1 s; poll a few times rather than relying on
    # the first receive returning the message.
    bodies = []
    for _ in range(5):
        rec_res = api.get("/aws/sqs/messages", params={"queue_name": queue_name})
        assert rec_res.status_code == 200, rec_res.text
        bodies += [m["body"] for m in rec_res.json()["messages"]]
        if bodies:
            break
    assert bodies == ["hello pytest"]


def test_aws_dynamodb_lifecycle(api, table_name):
    """Verify creating a DynamoDB table, putting, updating and scanning items."""
    create_res = api.post("/aws/dynamodb/tables", json={"table_name": table_name, "key_name": "id"})
    assert create_res.status_code == 200, create_res.text
    assert create_res.json()["status"] == "created"

    put_res = api.post("/aws/dynamodb/items", json={"table_name": table_name, "item": {"id": "1", "name": "Item One"}})
    assert put_res.status_code == 200, put_res.text

    scan_res = api.get("/aws/dynamodb/items", params={"table_name": table_name})
    assert scan_res.status_code == 200
    assert scan_res.json()["items"] == [{"id": "1", "name": "Item One"}]

    update_res = api.put(
        "/aws/dynamodb/items",
        json={"table_name": table_name, "item": {"id": "1", "name": "Item One Updated", "price": 99.99}},
    )
    assert update_res.status_code == 200, update_res.text

    scan_updated = api.get("/aws/dynamodb/items", params={"table_name": table_name})
    assert scan_updated.status_code == 200
    updated_item = next(it for it in scan_updated.json()["items"] if str(it.get("id")) == "1")
    assert updated_item["name"] == "Item One Updated"
    assert updated_item["price"] == 99.99

    delete_res = api.delete(
        "/aws/dynamodb/items", params={"table_name": table_name, "key_name": "id", "key_value": "1"}
    )
    assert delete_res.status_code == 200, delete_res.text
    assert api.get("/aws/dynamodb/items", params={"table_name": table_name}).json()["items"] == []


def test_aws_secrets_lifecycle(api, secret_name):
    """Verify creating, reading, updating and listing a Secrets Manager secret."""
    created = api.post("/aws/secrets", json={"name": secret_name, "value": "v1"})
    assert created.status_code == 200, created.text
    assert created.json() == {"status": "created", "name": secret_name}

    got = api.get(f"/aws/secrets/{secret_name}")
    assert got.status_code == 200, got.text
    assert got.json() == {"name": secret_name, "value": "v1"}

    updated = api.post("/aws/secrets", json={"name": secret_name, "value": "v2"})
    assert updated.status_code == 200, updated.text
    assert updated.json() == {"status": "updated", "name": secret_name}
    assert api.get(f"/aws/secrets/{secret_name}").json()["value"] == "v2"

    listed = api.get("/aws/secrets")
    assert listed.status_code == 200
    assert secret_name in [s["name"] for s in listed.json()["secrets"]]


def test_aws_eventbridge_lifecycle(api):
    """Verify listing event buses and publishing an event."""
    buses_res = api.get("/aws/events/buses")
    assert buses_res.status_code == 200
    assert any(b["name"] == "default" for b in buses_res.json()["buses"])

    put_res = api.post(
        "/aws/events/put-event",
        json={
            "source": "pytest.test",
            "detail_type": "TestRun",
            "detail": {"status": "passed"},
            "event_bus_name": "default",
        },
    )
    assert put_res.status_code == 200, put_res.text
    assert put_res.json()["status"] == "published"


def test_aws_kinesis_lifecycle(api, stream_name):
    """Verify creating a Kinesis stream, putting a record, listing streams and reading it back."""
    create_res = api.post("/aws/kinesis/streams", json={"stream_name": stream_name, "shard_count": 1})
    assert create_res.status_code == 200, create_res.text

    list_res = api.get("/aws/kinesis/streams")
    assert list_res.status_code == 200
    assert any(s["name"] == stream_name for s in list_res.json()["streams"])

    # put_kinesis_record waits for the new stream to become ACTIVE.
    put_res = api.post(
        "/aws/kinesis/records",
        json={"stream_name": stream_name, "partition_key": "part_1", "data": "kinesis-test-data"},
        timeout=60,
    )
    assert put_res.status_code == 200, put_res.text
    assert put_res.json()["status"] == "success"

    read_res = api.get("/aws/kinesis/records", params={"stream_name": stream_name})
    assert read_res.status_code == 200, read_res.text
    assert "kinesis-test-data" in [r["data"] for r in read_res.json()["records"]]


def test_aws_lambda_lifecycle(api, function_name, deploy_lambda, invoke_lambda):
    """Verify creating, listing, invoking and deleting a Lambda function."""
    create_res = deploy_lambda(
        function_name,
        "def lambda_handler(event, context):\n    return {'status': 'ok', 'msg': 'hello lambda', 'received': event}\n",
    )
    assert create_res.status_code == 200, create_res.text
    assert create_res.json()["status"] == "created"

    list_res = api.get("/aws/lambda/functions")
    assert list_res.status_code == 200
    assert any(f["name"] == function_name for f in list_res.json()["functions"])

    invoke_res = invoke_lambda(function_name, {"user": "test_runner"})
    assert invoke_res.status_code == 200, invoke_res.text
    data = invoke_res.json()
    assert data["executed"] is True
    assert data["result"]["status"] == "ok"
    assert data["result"]["received"]["user"] == "test_runner"

    deleted = api.delete("/aws/lambda/functions", params={"name": function_name})
    assert deleted.status_code == 200, deleted.text
    # Deletion may take a moment to show up in LocalStack's listing.
    deadline = time.monotonic() + 15
    while any(f["name"] == function_name for f in api.get("/aws/lambda/functions").json()["functions"]):
        assert time.monotonic() < deadline, "deleted function still listed"
        time.sleep(1)


# ------------------------------------------------------------------------------
# Not-found errors not covered elsewhere (see test_backend_errors_cache.py for
# SQS, secrets, DynamoDB scan, Lambda invoke and S3 download)
# ------------------------------------------------------------------------------


def test_delete_unknown_dynamodb_table_returns_404(api):
    """Verify deleting a table that does not exist is a 404."""
    res = api.delete("/aws/dynamodb/tables", params={"table_name": unique_name("missing_table")})
    assert res.status_code == 404, res.text


def test_delete_unknown_lambda_function_returns_404(api):
    """Verify deleting a function that does not exist is a 404."""
    res = api.delete("/aws/lambda/functions", params={"name": unique_name("missing-fn")})
    assert res.status_code == 404, res.text


def test_put_record_to_unknown_kinesis_stream_returns_404(api):
    """Verify writing to a stream that does not exist is a 404."""
    res = api.post(
        "/aws/kinesis/records",
        json={"stream_name": unique_name("missing-stream"), "partition_key": "pk", "data": "x"},
        timeout=60,
    )
    assert res.status_code == 404, res.text


def test_purge_unknown_sqs_queue_returns_404(api):
    """Verify purging a queue that does not exist is a 404."""
    res = api.delete("/aws/sqs/queues", params={"queue_name": unique_name("missing-queue")})
    assert res.status_code == 404, res.text
