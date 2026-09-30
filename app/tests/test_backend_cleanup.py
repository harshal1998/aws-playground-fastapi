"""
Regression tests for #35 (backend cleanup): paginated AWS listings.

Unit tests drive real boto3 clients through botocore's Stubber, so the
actual request parameters (MaxResults, NextToken, ContinuationToken, ...)
are checked without needing LocalStack.
"""
import datetime

from botocore.stub import ANY, Stubber

from app.services.aws import AWSService
from app.services.s3 import S3Service

NOW = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)


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
