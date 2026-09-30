"""
Unified AWS Services Integration for LocalStack.
Provides a class-based AWSService managing SQS, DynamoDB, Secrets Manager, Lambda, EventBridge, and Kinesis.
"""
import base64
import http.client
import io
import json
import time
import urllib.request
import zipfile
from decimal import Decimal
from functools import cached_property
from typing import Any

import boto3
from boto3.dynamodb.types import Binary, TypeDeserializer, TypeSerializer
from botocore.exceptions import ClientError, WaiterError

from app.core.boto import BOTO_CLIENT_CONFIG
from app.core.config import settings

_SERIALIZER = TypeSerializer()
_DESERIALIZER = TypeDeserializer()

SQS_QUEUE_MISSING_CODES = frozenset({"QueueDoesNotExist", "AWS.SimpleQueueService.NonExistentQueue"})

LOCALSTACK_HEALTH_TIMEOUT_SECONDS = 3
# What get_localstack_health() raises when LocalStack is unreachable, times
# out, drops the connection mid-response or doesn't return JSON.
LOCALSTACK_HEALTH_ERRORS = (OSError, ValueError, http.client.HTTPException)

LAMBDA_TIMEOUT_SECONDS = 15
# Bounded polling for Lambda state transitions: at most ~20s per wait.
LAMBDA_WAITER_CONFIG = {"Delay": 1, "MaxAttempts": 20}


class AWSService:
    """Unified service class for interacting with LocalStack AWS services."""

    def __init__(
        self,
        endpoint_url: str = settings.AWS_ENDPOINT_URL,
        region_name: str = settings.AWS_REGION,
        aws_access_key_id: str = settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key: str = settings.AWS_SECRET_ACCESS_KEY,
    ):
        self.endpoint_url = endpoint_url
        self.region_name = region_name
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        # SQS queue name -> URL, so repeated operations skip GetQueueUrl.
        # Plain dict get/set/pop are atomic under the GIL; a race at worst
        # looks the same URL up twice.
        self._queue_urls: dict[str, str] = {}

    def _get_boto_client(self, service_name: str):
        """Initializes a boto3 client configured for LocalStack."""
        return boto3.client(
            service_name,
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
            region_name=self.region_name,
            config=BOTO_CLIENT_CONFIG,
        )

    # Cached boto3 clients
    @cached_property
    def sqs(self):
        """Cached SQS boto3 client."""
        return self._get_boto_client("sqs")

    @cached_property
    def dynamodb(self):
        """Cached DynamoDB boto3 client."""
        return self._get_boto_client("dynamodb")

    @cached_property
    def secretsmanager(self):
        """Cached Secrets Manager boto3 client."""
        return self._get_boto_client("secretsmanager")

    @cached_property
    def lambda_client(self):
        """Cached Lambda boto3 client."""
        return self._get_boto_client("lambda")

    @cached_property
    def events(self):
        """Cached EventBridge boto3 client."""
        return self._get_boto_client("events")

    @cached_property
    def kinesis(self):
        """Cached Kinesis boto3 client."""
        return self._get_boto_client("kinesis")

    # --------------------------------------------------------------------------
    # 1. LocalStack Health & Status
    # --------------------------------------------------------------------------
    def get_localstack_health(self) -> dict[str, Any]:
        """Fetches the raw JSON from LocalStack's health endpoint.

        Raises one of LOCALSTACK_HEALTH_ERRORS if it can't be fetched.
        """
        req = urllib.request.Request(
            f"{self.endpoint_url}/_localstack/health", headers={"User-Agent": "FastAPI-Health"}
        )
        with urllib.request.urlopen(req, timeout=LOCALSTACK_HEALTH_TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode())

    def get_localstack_status(self) -> dict[str, Any]:
        """Summarizes LocalStack's health: online/offline and its active services."""
        try:
            data = self.get_localstack_health()
            services = data.get("services", {})
            active_services = [k for k, v in services.items() if v in ("available", "running")]
            return {
                "status": "online",
                "version": data.get("version", "3.8.0"),
                "edition": data.get("edition", "community"),
                "active_services": sorted(active_services),
                "total_available": len(active_services),
            }
        except (*LOCALSTACK_HEALTH_ERRORS, AttributeError) as e:
            # AttributeError: the health JSON wasn't the expected object shape
            return {
                "status": "offline",
                "error": str(e),
                "active_services": [],
                "total_available": 0,
            }

    # --------------------------------------------------------------------------
    # 2. SQS Operations
    # --------------------------------------------------------------------------
    def list_sqs_queues(self) -> list[dict[str, Any]]:
        """Lists all SQS queues with message counts.

        Errors from ListQueues propagate (mapped to an HTTP status by the API
        exception handlers); a queue deleted mid-listing just reports 0 counts.
        """
        resp = self.sqs.list_queues()
        queue_urls = resp.get("QueueUrls", [])
        result = []
        for url in queue_urls:
            name = url.split("/")[-1]
            try:
                attrs = self.sqs.get_queue_attributes(
                    QueueUrl=url,
                    AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"],
                ).get("Attributes", {})
                msg_count = int(attrs.get("ApproximateNumberOfMessages", 0))
                in_flight = int(attrs.get("ApproximateNumberOfMessagesNotVisible", 0))
            except ClientError:
                msg_count, in_flight = 0, 0
            result.append({
                "name": name,
                "url": url,
                "messages": msg_count,
                "in_flight": in_flight,
            })
        return result

    def _queue_url(self, queue_name: str) -> str:
        """Returns the queue URL, calling GetQueueUrl only on the first use of a name."""
        url = self._queue_urls.get(queue_name)
        if url is None:
            url = self.sqs.get_queue_url(QueueName=queue_name)["QueueUrl"]
            self._queue_urls[queue_name] = url
        return url

    def _on_queue(self, queue_name: str, operation, **kwargs) -> dict[str, Any]:
        """Runs an SQS operation against a queue by name via its cached URL.

        If the queue no longer exists, its cached URL is dropped before the
        error propagates, so a recreated queue is looked up afresh.
        """
        q_url = self._queue_url(queue_name)
        try:
            return operation(QueueUrl=q_url, **kwargs)
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in SQS_QUEUE_MISSING_CODES:
                self._queue_urls.pop(queue_name, None)
            raise

    def create_sqs_queue(self, queue_name: str) -> dict[str, Any]:
        """Creates a new SQS queue."""
        clean_name = queue_name.strip()
        resp = self.sqs.create_queue(QueueName=clean_name)
        self._queue_urls[clean_name] = resp["QueueUrl"]
        return {"name": clean_name, "url": resp["QueueUrl"]}

    def send_sqs_message(self, queue_name: str, message_body: str) -> dict[str, Any]:
        """Sends a message payload to an SQS queue."""
        resp = self._on_queue(queue_name, self.sqs.send_message, MessageBody=message_body)
        return {"message_id": resp.get("MessageId"), "status": "sent"}

    def receive_sqs_messages(self, queue_name: str, max_messages: int = 5) -> list[dict[str, Any]]:
        """Receives up to max_messages from an SQS queue without deleting."""
        resp = self._on_queue(
            queue_name, self.sqs.receive_message, MaxNumberOfMessages=max_messages, WaitTimeSeconds=1
        )
        msgs = resp.get("Messages", [])
        return [
            {
                "id": m.get("MessageId"),
                "receipt_handle": m.get("ReceiptHandle"),
                "body": m.get("Body"),
            }
            for m in msgs
        ]

    def purge_sqs_queue(self, queue_name: str) -> dict[str, str]:
        """Purges all messages from an SQS queue."""
        self._on_queue(queue_name, self.sqs.purge_queue)
        return {"status": "purged", "queue": queue_name}

    # --------------------------------------------------------------------------
    # 3. DynamoDB Operations
    # --------------------------------------------------------------------------
    def list_dynamodb_tables(self) -> list[dict[str, Any]]:
        """Lists DynamoDB tables with item counts and partition keys."""
        resp = self.dynamodb.list_tables()
        table_names = resp.get("TableNames", [])
        result = []
        for name in table_names:
            try:
                desc = self.dynamodb.describe_table(TableName=name).get("Table", {})
                item_count = desc.get("ItemCount", 0)
                status = desc.get("TableStatus", "ACTIVE")
                key_schema = desc.get("KeySchema", [])
                partition_key = key_schema[0]["AttributeName"] if key_schema else "id"
            except ClientError:
                # e.g. the table was deleted between ListTables and DescribeTable
                item_count, status, partition_key = 0, "UNKNOWN", "id"
            result.append({
                "name": name,
                "item_count": item_count,
                "status": status,
                "partition_key": partition_key,
            })
        return result

    def create_dynamodb_table(self, table_name: str, key_name: str = "id") -> dict[str, Any]:
        """Creates a simple DynamoDB table with a string partition key."""
        try:
            self.dynamodb.create_table(
                TableName=table_name,
                KeySchema=[{"AttributeName": key_name, "KeyType": "HASH"}],
                AttributeDefinitions=[{"AttributeName": key_name, "AttributeType": "S"}],
                BillingMode="PAY_PER_REQUEST",
            )
            return {"status": "created", "table": table_name, "partition_key": key_name}
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "ResourceInUseException":
                return {"status": "already_exists", "table": table_name}
            raise

    def delete_dynamodb_table(self, table_name: str) -> dict[str, str]:
        """Deletes a DynamoDB table."""
        self.dynamodb.delete_table(TableName=table_name)
        return {"status": "deleted", "table": table_name}

    @staticmethod
    def _to_dynamodb_compatible(value: Any) -> Any:
        """Recursively converts floats to Decimal so TypeSerializer accepts them.

        str() is used so 99.99 becomes Decimal("99.99") rather than the
        binary expansion of the float.
        """
        if isinstance(value, float):
            return Decimal(str(value))
        if isinstance(value, dict):
            return {k: AWSService._to_dynamodb_compatible(v) for k, v in value.items()}
        if isinstance(value, list):
            return [AWSService._to_dynamodb_compatible(v) for v in value]
        return value

    @staticmethod
    def _to_json_compatible(value: Any) -> Any:
        """Recursively converts deserialized DynamoDB values into JSON-friendly types.

        Decimal becomes int when integral and float otherwise, sets become
        lists and binary values become base64 strings.
        """
        if isinstance(value, Decimal):
            return int(value) if value == value.to_integral_value() else float(value)
        if isinstance(value, dict):
            return {k: AWSService._to_json_compatible(v) for k, v in value.items()}
        if isinstance(value, (list, set, frozenset)):
            return [AWSService._to_json_compatible(v) for v in value]
        if isinstance(value, Binary):
            return base64.b64encode(value.value).decode("ascii")
        if isinstance(value, (bytes, bytearray)):
            return base64.b64encode(bytes(value)).decode("ascii")
        return value

    def scan_dynamodb_items(self, table_name: str, limit: int = 50) -> list[dict[str, Any]]:
        """Scans and returns items from a DynamoDB table as plain JSON values."""
        resp = self.dynamodb.scan(TableName=table_name, Limit=limit)
        return [
            {k: self._to_json_compatible(_DESERIALIZER.deserialize(v)) for k, v in item.items()}
            for item in resp.get("Items", [])
        ]

    def put_dynamodb_item(self, table_name: str, item_dict: dict[str, Any]) -> dict[str, str]:
        """Inserts a document into a DynamoDB table using native attribute types."""
        dynamo_item = {
            k: _SERIALIZER.serialize(self._to_dynamodb_compatible(v))
            for k, v in item_dict.items()
        }
        self.dynamodb.put_item(TableName=table_name, Item=dynamo_item)
        return {"status": "inserted", "table": table_name}

    def delete_dynamodb_item(self, table_name: str, key_name: str, key_value: str) -> dict[str, str]:
        """Deletes an item from a DynamoDB table by partition key."""
        self.dynamodb.delete_item(TableName=table_name, Key={key_name: {"S": str(key_value)}})
        return {"status": "deleted", "table": table_name, "key": key_value}

    # --------------------------------------------------------------------------
    # 4. Secrets Manager Operations
    # --------------------------------------------------------------------------
    def list_secrets(self) -> list[dict[str, Any]]:
        """Lists all secrets stored in Secrets Manager."""
        resp = self.secretsmanager.list_secrets()
        secrets_list = resp.get("SecretList", [])
        return [
            {
                "name": s.get("Name"),
                "arn": s.get("ARN"),
                "last_changed": s.get("LastChangedDate", "").isoformat() if hasattr(s.get("LastChangedDate"), "isoformat") else str(s.get("LastChangedDate", "")),
            }
            for s in secrets_list
        ]

    def get_secret(self, secret_name: str) -> dict[str, Any]:
        """Retrieves secret string by name."""
        resp = self.secretsmanager.get_secret_value(SecretId=secret_name)
        return {"name": secret_name, "value": resp.get("SecretString", "")}

    def create_or_update_secret(self, secret_name: str, secret_value: str) -> dict[str, str]:
        """Creates a new secret or updates an existing one."""
        try:
            self.secretsmanager.create_secret(Name=secret_name, SecretString=secret_value)
            return {"status": "created", "name": secret_name}
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "ResourceExistsException":
                self.secretsmanager.put_secret_value(SecretId=secret_name, SecretString=secret_value)
                return {"status": "updated", "name": secret_name}
            raise

    # --------------------------------------------------------------------------
    # 5. AWS Lambda Operations
    # --------------------------------------------------------------------------
    def list_lambda_functions(self) -> list[dict[str, Any]]:
        """Lists all deployed Lambda functions."""
        resp = self.lambda_client.list_functions()
        functions = resp.get("Functions", [])
        return [
            {
                "name": fn.get("FunctionName"),
                "runtime": fn.get("Runtime", "python3.11"),
                "handler": fn.get("Handler", "handler.lambda_handler"),
                "code_size": fn.get("CodeSize", 0),
                "timeout": fn.get("Timeout", 3),
                "last_modified": fn.get("LastModified", ""),
                "description": fn.get("Description", ""),
            }
            for fn in functions
        ]

    def create_lambda_function(
        self,
        function_name: str,
        code_str: str = "def lambda_handler(event, context):\n    return {'message': 'Hello from LocalStack Lambda!', 'event': event}\n",
        runtime: str = "python3.11",
        handler: str = "handler.lambda_handler",
        description: str = "",
    ) -> dict[str, Any]:
        """Creates or deploys a Python Lambda function from a code string."""
        clean_name = function_name.strip()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            info = zipfile.ZipInfo("handler.py")
            info.external_attr = 0o755 << 16
            z.writestr(info, code_str)
        buf.seek(0)
        zip_bytes = buf.read()

        role = "arn:aws:iam::000000000000:role/lambda-role"
        desc = description or f"Local Lambda {clean_name}"
        try:
            resp = self.lambda_client.create_function(
                FunctionName=clean_name,
                Runtime=runtime,
                Role=role,
                Handler=handler,
                Code={"ZipFile": zip_bytes},
                Description=desc,
                Timeout=LAMBDA_TIMEOUT_SECONDS,
            )
            state = self._wait_for_lambda(clean_name, "function_active_v2")
            return {"status": "created", "name": clean_name, "arn": resp.get("FunctionArn"), "state": state}
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") != "ResourceConflictException":
                raise

        # The function already exists: update it in place so its ARN,
        # permissions and event source mappings are preserved.
        resp = self.lambda_client.update_function_code(FunctionName=clean_name, ZipFile=zip_bytes)
        state = self._wait_for_lambda(clean_name, "function_updated_v2")
        if (
            resp.get("Runtime") != runtime
            or resp.get("Handler") != handler
            or resp.get("Description") != desc
            or resp.get("Timeout") != LAMBDA_TIMEOUT_SECONDS
        ):
            resp = self.lambda_client.update_function_configuration(
                FunctionName=clean_name,
                Runtime=runtime,
                Handler=handler,
                Description=desc,
                Timeout=LAMBDA_TIMEOUT_SECONDS,
            )
            state = self._wait_for_lambda(clean_name, "function_updated_v2")
        return {"status": "updated", "name": clean_name, "arn": resp.get("FunctionArn"), "state": state}

    def _wait_for_lambda(self, function_name: str, waiter_name: str) -> str:
        """Waits for a Lambda function to settle using a bounded boto3 waiter.

        waiter_name is "function_active_v2" after a create or
        "function_updated_v2" after a code/configuration update. Returns
        "ready" on success, or "pending" if the waiter gave up (LocalStack
        can be slow to start a runtime), so callers never block unbounded.
        """
        try:
            self.lambda_client.get_waiter(waiter_name).wait(
                FunctionName=function_name, WaiterConfig=LAMBDA_WAITER_CONFIG
            )
            return "ready"
        except WaiterError as e:
            print(f"Lambda {function_name} not ready after {waiter_name}: {e}")
            return "pending"

    def invoke_lambda_function(self, function_name: str, payload: dict[str, Any] | str = "") -> dict[str, Any]:
        """Invokes a Lambda function and returns the execution payload.

        "executed" is False when the function itself failed (FunctionError is
        set on the invoke response); "result" then holds the error payload
        (errorMessage, errorType, stackTrace) and "error" the error kind.
        """
        # A freshly deployed function may still be Pending; the waiter returns
        # at once when it is Active and otherwise polls for a bounded time.
        self._wait_for_lambda(function_name, "function_active_v2")

        if isinstance(payload, dict):
            payload_bytes = json.dumps(payload).encode("utf-8")
        elif isinstance(payload, str) and payload.strip():
            payload_bytes = payload.strip().encode("utf-8")
        else:
            payload_bytes = b"{}"

        resp = self.lambda_client.invoke(FunctionName=function_name, Payload=payload_bytes)
        status_code = resp.get("StatusCode", 200)
        raw_result = resp["Payload"].read().decode("utf-8")
        try:
            result_json = json.loads(raw_result)
        except Exception:
            result_json = raw_result

        function_error = resp.get("FunctionError")
        result = {
            "status_code": status_code,
            "function": function_name,
            "executed": function_error is None,
            "result": result_json,
        }
        if function_error is not None:
            result["error"] = function_error
        return result

    def delete_lambda_function(self, function_name: str) -> dict[str, str]:
        """Deletes a Lambda function."""
        self.lambda_client.delete_function(FunctionName=function_name)
        return {"status": "deleted", "function": function_name}

    # --------------------------------------------------------------------------
    # 6. EventBridge Operations
    # --------------------------------------------------------------------------
    def list_event_buses(self) -> list[dict[str, Any]]:
        """Lists EventBridge event buses."""
        resp = self.events.list_event_buses()
        buses = resp.get("EventBuses", [])
        return [
            {
                "name": b.get("Name"),
                "arn": b.get("Arn"),
            }
            for b in buses
        ]

    def list_event_rules(self, event_bus_name: str = "default") -> list[dict[str, Any]]:
        """Lists rules for an event bus."""
        resp = self.events.list_rules(EventBusName=event_bus_name)
        rules = resp.get("Rules", [])
        return [
            {
                "name": r.get("Name"),
                "state": r.get("State"),
                "event_pattern": r.get("EventPattern", "{}"),
                "description": r.get("Description", ""),
            }
            for r in rules
        ]

    def put_event(
        self,
        source: str,
        detail_type: str,
        detail: dict[str, Any] | str,
        event_bus_name: str = "default",
    ) -> dict[str, Any]:
        """Publishes an event to EventBridge."""
        detail_str = json.dumps(detail) if isinstance(detail, dict) else str(detail)
        resp = self.events.put_events(
            Entries=[
                {
                    "Source": source,
                    "DetailType": detail_type,
                    "Detail": detail_str,
                    "EventBusName": event_bus_name,
                }
            ]
        )
        entries = resp.get("Entries", [])
        entry = entries[0] if entries else {}
        return {
            "status": "published",
            "event_id": entry.get("EventId"),
            "event_bus": event_bus_name,
            "failed_count": resp.get("FailedEntryCount", 0),
        }

    # --------------------------------------------------------------------------
    # 7. Kinesis Data Streams Operations
    # --------------------------------------------------------------------------
    def list_kinesis_streams(self) -> list[dict[str, Any]]:
        """Lists Kinesis streams with shard counts and status."""
        resp = self.kinesis.list_streams()
        names = resp.get("StreamNames", [])
        result = []
        for name in names:
            try:
                desc = self.kinesis.describe_stream_summary(StreamName=name).get("StreamDescriptionSummary", {})
                status = desc.get("StreamStatus", "ACTIVE")
                shards = desc.get("OpenShardCount", 1)
            except ClientError:
                status, shards = "ACTIVE", 1
            result.append({"name": name, "status": status, "open_shards": shards})
        return result

    def create_kinesis_stream(self, stream_name: str, shard_count: int = 1) -> dict[str, Any]:
        """Creates a new Kinesis data stream."""
        clean_name = stream_name.strip()
        try:
            self.kinesis.create_stream(StreamName=clean_name, ShardCount=shard_count)
            return {"status": "created", "stream": clean_name, "shards": shard_count}
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "ResourceInUseException":
                return {"status": "already_exists", "stream": clean_name}
            raise

    def delete_kinesis_stream(self, stream_name: str) -> dict[str, str]:
        """Deletes a Kinesis data stream."""
        self.kinesis.delete_stream(StreamName=stream_name)
        return {"status": "deleted", "stream": stream_name}

    def put_kinesis_record(self, stream_name: str, partition_key: str, data: str) -> dict[str, Any]:
        """Puts a data record into a Kinesis stream, waiting for ACTIVE state if newly created."""
        for _ in range(10):
            try:
                desc = self.kinesis.describe_stream_summary(StreamName=stream_name).get("StreamDescriptionSummary", {})
                if desc.get("StreamStatus") == "ACTIVE":
                    break
            except ClientError:
                pass  # not describable yet; PutRecord below reports a real error
            time.sleep(0.3)

        resp = self.kinesis.put_record(
            StreamName=stream_name,
            Data=data.encode("utf-8"),
            PartitionKey=partition_key,
        )
        return {
            "status": "success",
            "shard_id": resp.get("ShardId"),
            "sequence_number": resp.get("SequenceNumber"),
        }

    def get_kinesis_records(self, stream_name: str, limit: int = 20) -> list[dict[str, Any]]:
        """Reads recent records from a Kinesis stream."""
        desc = self.kinesis.describe_stream(StreamName=stream_name).get("StreamDescription", {})
        shards = desc.get("Shards", [])
        if not shards:
            return []
        shard_id = shards[0]["ShardId"]
        iter_resp = self.kinesis.get_shard_iterator(
            StreamName=stream_name,
            ShardId=shard_id,
            ShardIteratorType="TRIM_HORIZON",
        )
        shard_iter = iter_resp.get("ShardIterator")
        if not shard_iter:
            return []
        rec_resp = self.kinesis.get_records(ShardIterator=shard_iter, Limit=limit)
        records = rec_resp.get("Records", [])
        output = []
        for r in records:
            raw_data = r.get("Data", b"")
            try:
                payload = raw_data.decode("utf-8")
            except Exception:
                payload = str(raw_data)
            output.append({
                "sequence_number": r.get("SequenceNumber"),
                "partition_key": r.get("PartitionKey"),
                "approx_arrival": r.get("ApproximateArrivalTimestamp", "").isoformat() if hasattr(r.get("ApproximateArrivalTimestamp"), "isoformat") else str(r.get("ApproximateArrivalTimestamp")),
                "data": payload,
            })
        return output


# ------------------------------------------------------------------------------
# Dependency Provider (FastAPI Depends)
# ------------------------------------------------------------------------------
_aws_service: AWSService | None = None


def get_aws_service() -> AWSService:
    """Returns a singleton AWSService instance for FastAPI dependency injection."""
    global _aws_service
    if _aws_service is None:
        _aws_service = AWSService()
    return _aws_service
