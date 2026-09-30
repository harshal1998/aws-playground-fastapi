from fastapi import APIRouter, HTTPException, Query

from app.api.deps import AWSServiceDep
from app.schemas.aws import (
    DynamoItemCreate,
    DynamoTableCreate,
    EventBridgePut,
    KinesisRecordPut,
    KinesisStreamCreate,
    LambdaCreate,
    LambdaInvoke,
    SecretCreate,
    SQSMessageSend,
    SQSQueueCreate,
)

router = APIRouter()


@router.get("/health-raw")
def get_aws_health_raw(aws_service: AWSServiceDep):
    """Proxies the raw LocalStack health JSON — avoids CORS when called from the browser."""
    import json
    import urllib.request
    health_url = f"{aws_service.endpoint_url}/_localstack/health"
    try:
        req = urllib.request.Request(health_url, headers={"User-Agent": "FastAPI-HealthProxy"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LocalStack unreachable: {e}") from e


@router.get("/status")
def get_aws_status(aws_service: AWSServiceDep):
    """Returns LocalStack connection status and active AWS services."""
    return aws_service.get_localstack_status()


# --- SQS Endpoints ---
@router.get("/sqs/queues")
def list_queues(aws_service: AWSServiceDep):
    """Lists all SQS queues in LocalStack."""
    return {"queues": aws_service.list_sqs_queues()}


@router.post("/sqs/queues")
def create_queue(payload: SQSQueueCreate, aws_service: AWSServiceDep):
    """Creates a new SQS queue."""
    return aws_service.create_sqs_queue(payload.name)


@router.post("/sqs/messages")
def send_message(payload: SQSMessageSend, aws_service: AWSServiceDep):
    """Sends a message payload to an SQS queue."""
    return aws_service.send_sqs_message(payload.queue_name, payload.message_body)


@router.get("/sqs/messages")
def receive_messages(
    aws_service: AWSServiceDep,
    queue_name: str = Query(...),
    max_messages: int = Query(5, le=10),
):
    """Receives recent messages from an SQS queue."""
    return {"messages": aws_service.receive_sqs_messages(queue_name, max_messages)}


@router.delete("/sqs/queues")
def purge_queue(aws_service: AWSServiceDep, queue_name: str = Query(...)):
    """Purges all messages from an SQS queue."""
    return aws_service.purge_sqs_queue(queue_name)


# --- DynamoDB Endpoints ---
@router.get("/dynamodb/tables")
def list_tables(aws_service: AWSServiceDep):
    """Lists DynamoDB tables."""
    return {"tables": aws_service.list_dynamodb_tables()}


@router.post("/dynamodb/tables")
def create_table(payload: DynamoTableCreate, aws_service: AWSServiceDep):
    """Creates a DynamoDB table."""
    return aws_service.create_dynamodb_table(payload.table_name, payload.key_name)


@router.get("/dynamodb/items")
def scan_items(
    aws_service: AWSServiceDep,
    table_name: str = Query(...),
    limit: int = Query(20, le=50),
):
    """Scans items from a DynamoDB table."""
    return {"items": aws_service.scan_dynamodb_items(table_name, limit)}


@router.post("/dynamodb/items")
def put_item(payload: DynamoItemCreate, aws_service: AWSServiceDep):
    """Puts an item into a DynamoDB table."""
    return aws_service.put_dynamodb_item(payload.table_name, payload.item)


@router.put("/dynamodb/items")
def update_item(payload: DynamoItemCreate, aws_service: AWSServiceDep):
    """Updates an existing item in a DynamoDB table."""
    return aws_service.put_dynamodb_item(payload.table_name, payload.item)


@router.delete("/dynamodb/tables")
def delete_table(aws_service: AWSServiceDep, table_name: str = Query(...)):
    """Deletes a DynamoDB table."""
    return aws_service.delete_dynamodb_table(table_name)


@router.delete("/dynamodb/items")
def delete_item(
    aws_service: AWSServiceDep,
    table_name: str = Query(...),
    key_name: str = Query(...),
    key_value: str = Query(...),
):
    """Deletes an item from a DynamoDB table by partition key."""
    return aws_service.delete_dynamodb_item(table_name, key_name, key_value)


# --- Secrets Manager Endpoints ---
@router.get("/secrets")
def list_secrets(aws_service: AWSServiceDep):
    """Lists secrets in Secrets Manager."""
    return {"secrets": aws_service.list_secrets()}


@router.get("/secrets/{name:path}")
def get_secret(name: str, aws_service: AWSServiceDep):
    """Retrieves secret string by name."""
    return aws_service.get_secret(name)


@router.post("/secrets")
def create_secret(payload: SecretCreate, aws_service: AWSServiceDep):
    """Creates or updates a secret."""
    return aws_service.create_or_update_secret(payload.name, payload.value)


# --- Lambda Endpoints ---
@router.get("/lambda/functions")
def list_lambda_functions(aws_service: AWSServiceDep):
    """Lists deployed Lambda functions."""
    return {"functions": aws_service.list_lambda_functions()}


@router.post("/lambda/functions")
def create_lambda_function(payload: LambdaCreate, aws_service: AWSServiceDep):
    """Creates a Python Lambda function, or updates its code in place if it exists.

    Returns "status": "created" or "updated"; the ARN is kept on update.
    """
    return aws_service.create_lambda_function(
        function_name=payload.name,
        code_str=payload.code,
        runtime=payload.runtime,
        handler=payload.handler,
        description=payload.description,
    )


@router.post("/lambda/invoke")
def invoke_lambda_function(payload: LambdaInvoke, aws_service: AWSServiceDep):
    """Invokes a Lambda function with a custom payload.

    Returns 200 whenever the invoke call itself succeeded, mirroring the AWS
    Invoke API: if the handler raised, the body has "executed": false, "error"
    set to the FunctionError kind and "result" set to the error payload. An
    error status means the invoke could not be made at all (e.g. 404 for an
    unknown function, 503 if LocalStack is unreachable).
    """
    return aws_service.invoke_lambda_function(payload.name, payload.payload)


@router.delete("/lambda/functions")
def delete_lambda_function(aws_service: AWSServiceDep, name: str = Query(...)):
    """Deletes a Lambda function."""
    return aws_service.delete_lambda_function(name)


# --- EventBridge Endpoints ---
@router.get("/events/buses")
def list_event_buses(aws_service: AWSServiceDep):
    """Lists EventBridge event buses."""
    return {"buses": aws_service.list_event_buses()}


@router.get("/events/rules")
def list_event_rules(aws_service: AWSServiceDep, event_bus: str = Query("default")):
    """Lists rules on an event bus."""
    return {"rules": aws_service.list_event_rules(event_bus)}


@router.post("/events/put-event")
def put_event(payload: EventBridgePut, aws_service: AWSServiceDep):
    """Publishes a test event to EventBridge."""
    return aws_service.put_event(
        source=payload.source,
        detail_type=payload.detail_type,
        detail=payload.detail,
        event_bus_name=payload.event_bus_name,
    )


# --- Kinesis Endpoints ---
@router.get("/kinesis/streams")
def list_kinesis_streams(aws_service: AWSServiceDep):
    """Lists Kinesis data streams."""
    return {"streams": aws_service.list_kinesis_streams()}


@router.post("/kinesis/streams")
def create_kinesis_stream(payload: KinesisStreamCreate, aws_service: AWSServiceDep):
    """Creates a new Kinesis stream."""
    return aws_service.create_kinesis_stream(payload.stream_name, payload.shard_count)


@router.delete("/kinesis/streams")
def delete_kinesis_stream(aws_service: AWSServiceDep, name: str = Query(...)):
    """Deletes a Kinesis stream."""
    return aws_service.delete_kinesis_stream(name)


@router.post("/kinesis/records")
def put_kinesis_record(payload: KinesisRecordPut, aws_service: AWSServiceDep):
    """Puts a data record into a Kinesis stream."""
    return aws_service.put_kinesis_record(payload.stream_name, payload.partition_key, payload.data)


@router.get("/kinesis/records")
def get_kinesis_records(aws_service: AWSServiceDep, stream_name: str = Query(...), limit: int = Query(20, le=50)):
    """Reads records from a Kinesis stream."""
    return {"records": aws_service.get_kinesis_records(stream_name, limit)}
