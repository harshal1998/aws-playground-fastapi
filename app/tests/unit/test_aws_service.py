"""AWSService against moto's in-memory SQS, DynamoDB, Secrets Manager, Kinesis and Lambda."""
import json

import pytest
from botocore.exceptions import ClientError

# ------------------------------------------------------------------------------
# SQS
# ------------------------------------------------------------------------------


def test_sqs_create_send_receive_purge(aws_service):
    """Verify a queue round-trip: create, send, receive (without deleting), purge."""
    created = aws_service.create_sqs_queue("  orders  ")
    assert created["name"] == "orders"
    assert created["url"].endswith("/orders")

    aws_service.send_sqs_message("orders", "first")
    aws_service.send_sqs_message("orders", "second")
    received = aws_service.receive_sqs_messages("orders", max_messages=10)
    assert sorted(m["body"] for m in received) == ["first", "second"]
    assert all(m["receipt_handle"] for m in received)

    queues = {q["name"]: q for q in aws_service.list_sqs_queues()}
    assert queues["orders"]["in_flight"] == 2  # received but not deleted

    assert aws_service.purge_sqs_queue("orders") == {"status": "purged", "queue": "orders"}
    queues = {q["name"]: q for q in aws_service.list_sqs_queues()}
    assert (queues["orders"]["messages"], queues["orders"]["in_flight"]) == (0, 0)


def test_sqs_send_to_missing_queue_raises_and_caches_nothing(aws_service):
    """Verify a missing queue raises and leaves no stale URL in the cache."""
    with pytest.raises(ClientError):
        aws_service.send_sqs_message("nope", "hi")
    assert "nope" not in aws_service._queue_urls


# ------------------------------------------------------------------------------
# DynamoDB
# ------------------------------------------------------------------------------


def test_dynamodb_create_table_is_idempotent(aws_service):
    """Verify creating an existing table reports already_exists instead of failing."""
    assert aws_service.create_dynamodb_table("users")["status"] == "created"
    assert aws_service.create_dynamodb_table("users")["status"] == "already_exists"
    tables = {t["name"]: t for t in aws_service.list_dynamodb_tables()}
    assert tables["users"]["partition_key"] == "id"


def test_dynamodb_put_scan_round_trips_native_types(aws_service):
    """Verify floats, ints, bools, nulls, lists and maps survive put + scan as JSON values."""
    aws_service.create_dynamodb_table("products")
    item = {
        "id": "p-1",
        "price": 99.99,
        "stock": 3,
        "active": True,
        "discontinued": None,
        "tags": ["a", "b"],
        "dims": {"w": 1.5, "h": 2},
    }
    assert aws_service.put_dynamodb_item("products", item)["status"] == "inserted"

    scanned = aws_service.scan_dynamodb_items("products")
    assert scanned == [item]
    assert isinstance(scanned[0]["stock"], int)
    assert isinstance(scanned[0]["price"], float)


def test_dynamodb_delete_item(aws_service):
    """Verify an item deleted by partition key no longer scans."""
    aws_service.create_dynamodb_table("products")
    aws_service.put_dynamodb_item("products", {"id": "p-1"})
    aws_service.put_dynamodb_item("products", {"id": "p-2"})
    aws_service.delete_dynamodb_item("products", "id", "p-1")
    assert aws_service.scan_dynamodb_items("products") == [{"id": "p-2"}]


# ------------------------------------------------------------------------------
# Secrets Manager
# ------------------------------------------------------------------------------


def test_secret_create_get_update(aws_service):
    """Verify a secret is created, read back, then updated in place."""
    assert aws_service.create_or_update_secret("db/password", "s3cret") == {
        "status": "created",
        "name": "db/password",
    }
    assert aws_service.get_secret("db/password")["value"] == "s3cret"

    assert aws_service.create_or_update_secret("db/password", "rotated")["status"] == "updated"
    assert aws_service.get_secret("db/password")["value"] == "rotated"
    assert [s["name"] for s in aws_service.list_secrets()] == ["db/password"]


def test_get_missing_secret_raises_not_found(aws_service):
    """Verify reading an unknown secret raises ResourceNotFoundException."""
    with pytest.raises(ClientError) as exc:
        aws_service.get_secret("missing")
    assert exc.value.response["Error"]["Code"] == "ResourceNotFoundException"


# ------------------------------------------------------------------------------
# Kinesis
# ------------------------------------------------------------------------------


def test_kinesis_records_are_read_from_every_shard(aws_service):
    """Verify records put across two shards are all read back, oldest first."""
    assert aws_service.create_kinesis_stream("clicks", shard_count=2)["status"] == "created"
    assert aws_service.create_kinesis_stream("clicks", shard_count=2)["status"] == "already_exists"

    shards = set()
    sent = []
    for i in range(10):
        resp = aws_service.put_kinesis_record("clicks", partition_key=f"user-{i}", data=f"event-{i}")
        shards.add(resp["shard_id"])
        sent.append(f"event-{i}")
    assert len(shards) == 2, "partition keys should spread over both shards"

    records = aws_service.get_kinesis_records("clicks", limit=20)
    assert sorted(r["data"] for r in records) == sorted(sent)
    assert {r["partition_key"] for r in records} == {f"user-{i}" for i in range(10)}

    assert len(aws_service.get_kinesis_records("clicks", limit=4)) == 4


# ------------------------------------------------------------------------------
# Lambda (management only: moto needs Docker to actually invoke a function)
# ------------------------------------------------------------------------------


def test_lambda_create_update_delete(aws_service):
    """Verify deploying a function creates it, redeploying updates it, and delete removes it."""
    # moto checks the execution role exists (LocalStack doesn't).
    aws_service._session.client("iam").create_role(
        RoleName="lambda-role",
        AssumeRolePolicyDocument=json.dumps({
            "Version": "2012-10-17",
            "Statement": [
                {"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}
            ],
        }),
    )
    created = aws_service.create_lambda_function("hello")
    assert created["status"] == "created"
    assert created["state"] == "ready"

    updated = aws_service.create_lambda_function("hello", description="v2")
    assert updated["status"] == "updated"
    assert updated["arn"] == created["arn"]

    assert [f["name"] for f in aws_service.list_lambda_functions()] == ["hello"]
    aws_service.delete_lambda_function("hello")
    assert aws_service.list_lambda_functions() == []


@pytest.mark.skip(reason="moto runs Lambda invocations in Docker; covered by the integration suite")
def test_lambda_invoke():
    pass
