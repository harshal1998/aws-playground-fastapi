import os
import time

import requests

API_URL = os.getenv("API_URL", "http://localhost:8000")


def test_root_endpoint():
    """Verify the root health check endpoint returns 200 and expected payload."""
    response = requests.get(f"{API_URL}/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "container_id" in data


def test_create_and_read_item():
    """Verify creating an item in DB and retrieving it."""
    # 1. Create item
    payload = {
        "name": "Integration Test Keyboard",
        "price": 89.99,
        "is_offer": True,
    }
    create_res = requests.post(f"{API_URL}/items", json=payload)
    assert create_res.status_code == 201
    created_data = create_res.json()
    assert created_data["status"] == "created"
    item = created_data["item"]
    assert item["name"] == payload["name"]
    assert item["price"] == payload["price"]
    assert item["is_offer"] is True
    item_id = item["id"]

    # 2. Read single item by ID
    get_res = requests.get(f"{API_URL}/items/{item_id}")
    assert get_res.status_code == 200
    single_item = get_res.json()
    assert single_item["id"] == item_id
    assert single_item["name"] == payload["name"]


def test_create_item_rejects_non_positive_price():
    """Verify creating an item with a zero or negative price returns 422."""
    for bad_price in (0, -10.5):
        payload = {"name": "Invalid Price Item", "price": bad_price, "is_offer": False}
        response = requests.post(f"{API_URL}/items", json=payload)
        assert response.status_code == 422


def test_get_items_list():
    """Verify the items listing endpoint returns a valid list."""
    response = requests.get(f"{API_URL}/items?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "count" in data
    assert isinstance(data["items"], list)
    assert len(data["items"]) <= 5


def test_redis_cache_behavior():
    """Verify that repeating a query hits the Redis cache."""
    # First request: populates cache
    res1 = requests.get(f"{API_URL}/items?limit=3")
    assert res1.status_code == 200

    # Second request: must hit cache
    res2 = requests.get(f"{API_URL}/items?limit=3")
    assert res2.status_code == 200
    assert res2.json()["source"] == "cache (Redis)"


def test_prometheus_metrics():
    """Verify that the Prometheus /metrics endpoint is exposed and functioning."""
    response = requests.get(f"{API_URL}/metrics")
    assert response.status_code == 200
    assert (
        "http_requests_total" in response.text
        or "python_gc_objects_collected_total" in response.text
    )


def test_s3_upload_localstack():
    """Verify uploading a sample file to LocalStack S3."""
    response = requests.post(f"{API_URL}/s3/upload-sample?filename=test_doc.txt")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["bucket"] == "fastapi-bucket"
    assert data["key"] == "test_doc.txt"


def test_s3_list_objects():
    """Verify listing objects from LocalStack S3."""
    response = requests.get(f"{API_URL}/s3/objects")
    assert response.status_code == 200
    data = response.json()
    assert data["bucket"] == "fastapi-bucket"
    assert "objects" in data
    assert isinstance(data["objects"], list)


def test_item_not_found():
    """Verify requesting a non-existent item ID returns 404."""
    response = requests.get(f"{API_URL}/items/999999999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Item not found"


def test_aws_status():
    """Verify LocalStack AWS health status endpoint."""
    response = requests.get(f"{API_URL}/aws/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "s3" in data["active_services"]


def test_aws_sqs_lifecycle():
    """Verify creating an SQS queue and sending/receiving a message."""
    # 1. Create queue
    q_res = requests.post(f"{API_URL}/aws/sqs/queues", json={"name": "test-pytest-queue"})
    assert q_res.status_code == 200

    # 2. Send message
    send_res = requests.post(
        f"{API_URL}/aws/sqs/messages",
        json={"queue_name": "test-pytest-queue", "message_body": "hello pytest"},
    )
    assert send_res.status_code == 200

    # 3. Receive message
    rec_res = requests.get(f"{API_URL}/aws/sqs/messages?queue_name=test-pytest-queue")
    assert rec_res.status_code == 200
    msgs = rec_res.json().get("messages", [])
    assert len(msgs) > 0
    assert msgs[0]["body"] == "hello pytest"


def test_aws_dynamodb_lifecycle():
    """Verify creating a DynamoDB table and scanning items."""
    # Create table
    create_res = requests.post(
        f"{API_URL}/aws/dynamodb/tables",
        json={"table_name": "test_pytest_table", "key_name": "id"},
    )
    assert create_res.status_code == 200

    # Put item
    put_res = requests.post(
        f"{API_URL}/aws/dynamodb/items",
        json={"table_name": "test_pytest_table", "item": {"id": "1", "name": "Item One"}},
    )
    assert put_res.status_code == 200

    # Scan items
    scan_res = requests.get(f"{API_URL}/aws/dynamodb/items?table_name=test_pytest_table")
    assert scan_res.status_code == 200
    items = scan_res.json().get("items", [])
    assert len(items) > 0

    # Edit/Update item via PUT
    update_res = requests.put(
        f"{API_URL}/aws/dynamodb/items",
        json={"table_name": "test_pytest_table", "item": {"id": "1", "name": "Item One Updated", "price": 99.99}},
    )
    assert update_res.status_code == 200

    # Verify updated item
    scan_updated = requests.get(f"{API_URL}/aws/dynamodb/items?table_name=test_pytest_table")
    assert scan_updated.status_code == 200
    updated_item = next(it for it in scan_updated.json().get("items", []) if str(it.get("id")) == "1")
    assert updated_item["name"] == "Item One Updated"
    assert updated_item["price"] == 99.99


def test_aws_eventbridge_lifecycle():
    """Verify listing event buses and publishing an event."""
    buses_res = requests.get(f"{API_URL}/aws/events/buses")
    assert buses_res.status_code == 200
    buses = buses_res.json().get("buses", [])
    assert any(b["name"] == "default" for b in buses)

    put_res = requests.post(
        f"{API_URL}/aws/events/put-event",
        json={
            "source": "pytest.test",
            "detail_type": "TestRun",
            "detail": {"status": "passed"},
            "event_bus_name": "default",
        },
    )
    assert put_res.status_code == 200
    assert put_res.json()["status"] == "published"


def test_aws_kinesis_lifecycle():
    """Verify creating a Kinesis stream, putting a record, and listing streams."""
    stream_name = "test-pytest-stream"
    create_res = requests.post(
        f"{API_URL}/aws/kinesis/streams",
        json={"stream_name": stream_name, "shard_count": 1},
    )
    assert create_res.status_code == 200

    list_res = requests.get(f"{API_URL}/aws/kinesis/streams")
    assert list_res.status_code == 200
    streams = list_res.json().get("streams", [])
    assert any(s["name"] == stream_name for s in streams)

    put_res = requests.post(
        f"{API_URL}/aws/kinesis/records",
        json={"stream_name": stream_name, "partition_key": "part_1", "data": "kinesis-test-data"},
    )
    assert put_res.status_code == 200
    assert put_res.json()["status"] == "success"


def test_aws_lambda_lifecycle():
    """Verify creating, listing, and invoking a Lambda function."""
    fn_name = "pytest_demo_fn"
    create_res = requests.post(
        f"{API_URL}/aws/lambda/functions",
        json={
            "name": fn_name,
            "code": "def lambda_handler(event, context):\n    return {'status': 'ok', 'msg': 'hello lambda', 'received': event}\n",
        },
    )
    assert create_res.status_code == 200

    list_res = requests.get(f"{API_URL}/aws/lambda/functions")
    assert list_res.status_code == 200
    fns = list_res.json().get("functions", [])
    assert any(f["name"] == fn_name for f in fns)

    # LocalStack takes a moment to move a freshly created function out of
    # "Pending" state, so retry briefly instead of failing on a cold invoke.
    for attempt in range(5):
        invoke_res = requests.post(
            f"{API_URL}/aws/lambda/invoke",
            json={"name": fn_name, "payload": {"user": "test_runner"}},
        )
        if invoke_res.status_code == 200 or attempt == 4:
            break
        time.sleep(2)
    assert invoke_res.status_code == 200
    data = invoke_res.json()
    assert data["executed"] is True
    assert data["result"]["status"] == "ok"
    assert data["result"]["received"]["user"] == "test_runner"

