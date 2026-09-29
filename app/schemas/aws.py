from typing import Any

from pydantic import BaseModel, Field


class SQSQueueCreate(BaseModel):
    name: str


class SQSMessageSend(BaseModel):
    queue_name: str
    message_body: str


class DynamoTableCreate(BaseModel):
    table_name: str
    key_name: str = "id"


class DynamoItemCreate(BaseModel):
    table_name: str
    item: dict[str, Any]


class SecretCreate(BaseModel):
    name: str
    value: str


class LambdaCreate(BaseModel):
    name: str
    code: str = (
        "def lambda_handler(event, context):\n"
        "    return {'message': 'Hello from LocalStack Lambda!', 'event': event}\n"
    )
    runtime: str = "python3.11"
    handler: str = "handler.lambda_handler"
    description: str = ""


class LambdaInvoke(BaseModel):
    name: str
    payload: Any = Field(default_factory=dict)


class EventBridgePut(BaseModel):
    source: str = "custom.fastapi.app"
    detail_type: str = "NotificationSent"
    detail: Any = Field(default_factory=lambda: {"status": "success"})
    event_bus_name: str = "default"


class KinesisStreamCreate(BaseModel):
    stream_name: str
    shard_count: int = 1


class KinesisRecordPut(BaseModel):
    stream_name: str
    partition_key: str = "partition_1"
    data: str
