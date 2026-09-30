"""
Maps boto3/botocore errors to HTTP responses in one place.

Endpoints let ClientError / BotoCoreError propagate; the handlers registered
by register_exception_handlers() turn them into {"detail": ...} responses
with a status that reflects what went wrong:

- not-found error codes            -> 404
- validation / bad-parameter codes -> 400
- conflict / in-use codes          -> 409
- throttling codes                 -> 429
- LocalStack unreachable/timed out -> 503
- anything else from AWS           -> 502 (bad gateway: the upstream failed)
"""
import logging

from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    HTTPClientError,
    ParamValidationError,
)
from botocore.exceptions import ConnectionError as BotoConnectionError
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

NOT_FOUND_CODES = frozenset({
    "ResourceNotFoundException",  # DynamoDB, Lambda, Secrets Manager, Kinesis, EventBridge
    "QueueDoesNotExist",  # SQS
    "AWS.SimpleQueueService.NonExistentQueue",  # SQS (query-compatible code)
    "NoSuchKey",  # S3
    "NoSuchBucket",  # S3
    "NotFound",
    "404",  # S3 HEAD requests
})

BAD_REQUEST_CODES = frozenset({
    "ValidationException",
    "ValidationError",
    "SerializationException",
    "InvalidParameterException",
    "InvalidParameterValueException",
    "InvalidParameterValue",
    "InvalidParameterCombination",
    "InvalidRequestException",
    "InvalidArgumentException",
    "InvalidArgument",
    "InvalidAttributeName",
    "InvalidAttributeValue",
    "InvalidBucketName",
    "InvalidEventPatternException",
    "InvalidRequestContentException",
    "MissingParameter",
    "MalformedQueryString",
    "AWS.SimpleQueueService.InvalidBatchEntryId",
    "InvalidMessageContents",
})

CONFLICT_CODES = frozenset({
    "ResourceInUseException",
    "ResourceConflictException",
    "ResourceExistsException",
    "ConditionalCheckFailedException",
    "TransactionConflictException",
    "BucketAlreadyExists",
    "BucketAlreadyOwnedByYou",
    "QueueAlreadyExists",
    "QueueNameExists",
    "QueueDeletedRecently",
    "AWS.SimpleQueueService.QueueDeletedRecently",
    "PurgeQueueInProgress",
    "AWS.SimpleQueueService.PurgeQueueInProgress",
})

THROTTLING_CODES = frozenset({
    "Throttling",
    "ThrottlingException",
    "ThrottledException",
    "TooManyRequestsException",
    "RequestLimitExceeded",
    "ProvisionedThroughputExceededException",
    "LimitExceededException",
    "SlowDown",
})

# Errors that mean LocalStack could not be reached or did not answer in time:
# ConnectionError covers EndpointConnectionError and ConnectTimeoutError,
# HTTPClientError covers ReadTimeoutError and ConnectionClosedError.
UNAVAILABLE_ERRORS = (BotoConnectionError, HTTPClientError)


def client_error_code(exc: ClientError) -> str:
    """Returns the AWS error code of a ClientError ("" if missing)."""
    return exc.response.get("Error", {}).get("Code", "") or ""


def status_for_client_error(exc: ClientError) -> int:
    """Picks the HTTP status for a ClientError based on its AWS error code."""
    code = client_error_code(exc)
    if code in NOT_FOUND_CODES:
        return 404
    if code in BAD_REQUEST_CODES:
        return 400
    if code in CONFLICT_CODES:
        return 409
    if code in THROTTLING_CODES:
        return 429
    if exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 404:
        return 404
    return 502


def status_for_botocore_error(exc: BotoCoreError) -> tuple[int, str]:
    """Picks the HTTP status and detail for a BotoCoreError (no AWS response)."""
    if isinstance(exc, UNAVAILABLE_ERRORS):
        return 503, f"LocalStack unavailable: {exc}"
    if isinstance(exc, ParamValidationError):
        return 400, str(exc)
    return 502, str(exc)


async def client_error_handler(request: Request, exc: ClientError) -> JSONResponse:
    status = status_for_client_error(exc)
    if status >= 500:
        logger.warning("AWS error on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(status_code=status, content={"detail": str(exc)})


async def botocore_error_handler(request: Request, exc: BotoCoreError) -> JSONResponse:
    status, detail = status_for_botocore_error(exc)
    if status >= 500:
        logger.warning("AWS error on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(status_code=status, content={"detail": detail})


def register_exception_handlers(app: FastAPI) -> None:
    """Registers the boto3/botocore exception handlers on the app."""
    app.add_exception_handler(ClientError, client_error_handler)
    app.add_exception_handler(BotoCoreError, botocore_error_handler)
