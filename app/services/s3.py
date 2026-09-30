"""
S3 Storage Integration for LocalStack/AWS.
Provides a class-based S3Service managing buckets and object storage.
"""
import socket
import threading
from functools import cached_property

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.boto import BOTO_CLIENT_CONFIG
from app.core.config import settings


class S3Service:
    """Class-based service for managing LocalStack/AWS S3 storage."""

    def __init__(
        self,
        endpoint_url: str = settings.AWS_ENDPOINT_URL,
        region_name: str = settings.AWS_REGION,
        aws_access_key_id: str = settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key: str = settings.AWS_SECRET_ACCESS_KEY,
        bucket_name: str = settings.S3_BUCKET_NAME,
    ):
        self.endpoint_url = endpoint_url
        self.region_name = region_name
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self.bucket_name = bucket_name
        # CreateBucket runs once (at startup, or lazily on first use if
        # LocalStack was down then) instead of before every operation.
        self._bucket_ready = False
        self._bucket_lock = threading.Lock()

    @cached_property
    def client(self):
        """Cached boto3 S3 client."""
        return boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
            region_name=self.region_name,
            config=BOTO_CLIENT_CONFIG,
        )

    def _create_bucket(self) -> None:
        """Creates the bucket (an existing one is fine) and marks it ready; raises on failure."""
        try:
            self.client.create_bucket(Bucket=self.bucket_name)
            print(f"Successfully initialized LocalStack S3 bucket: {self.bucket_name}")
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                raise
        self._bucket_ready = True

    def ensure_bucket_exists(self) -> None:
        """Best-effort bucket creation at startup; never raises.

        If it fails (e.g. LocalStack is still down), the first S3 operation
        retries it via _require_bucket().
        """
        try:
            self._create_bucket()
        except ClientError as e:
            print(f"Notice during S3 bucket initialization: {e}")
        except (BotoCoreError, OSError) as e:
            # EndpointConnectionError and botocore timeouts derive from
            # BotoCoreError, not OSError; never let them crash startup.
            print(f"LocalStack S3 connection skipped (service may be offline): {e}")

    def _require_bucket(self) -> None:
        """Creates the bucket once, lazily, if startup could not; errors propagate."""
        if self._bucket_ready:
            return
        with self._bucket_lock:
            if not self._bucket_ready:
                self._create_bucket()

    def _call(self, operation, **kwargs):
        """Runs an S3 client operation on the bucket, recreating it once if it vanished.

        The bucket is only created once per process, so if LocalStack restarts
        without persistence, NoSuchBucket resets that state and retries.
        """
        self._require_bucket()
        try:
            return operation(Bucket=self.bucket_name, **kwargs)
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") != "NoSuchBucket":
                raise
        self._bucket_ready = False
        self._require_bucket()
        return operation(Bucket=self.bucket_name, **kwargs)

    def list_bucket_objects(self) -> dict:
        """Lists all objects in the configured S3 bucket."""
        response = self._call(self.client.list_objects_v2)
        contents = response.get("Contents", [])
        objects = [
            {
                "key": obj["Key"],
                "size_bytes": obj["Size"],
                "last_modified": obj["LastModified"].isoformat(),
            }
            for obj in contents
        ]
        return {
            "bucket": self.bucket_name,
            "count": len(objects),
            "objects": objects,
        }

    def get_object_content(self, key: str) -> tuple[bytes, str]:
        """Retrieves object content and its content-type from S3."""
        obj = self._call(self.client.get_object, Key=key)
        content = obj["Body"].read()
        content_type = obj.get("ContentType", "application/octet-stream")
        return content, content_type

    def delete_object(self, key: str) -> None:
        """Deletes an object from the S3 bucket."""
        self._call(self.client.delete_object, Key=key)

    def put_object_content(
        self,
        key: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> dict:
        """Puts arbitrary byte content into S3 under the given key."""
        self._call(self.client.put_object, Key=key, Body=content, ContentType=content_type)
        return {
            "status": "success",
            "service": "LocalStack S3",
            "bucket": self.bucket_name,
            "key": key,
            "size_bytes": len(content),
        }

    def upload_sample_document(self, filename: str = "sample_report.txt") -> dict:
        """Uploads a test payload to the configured S3 bucket."""
        content = f"Uploaded from FastAPI container {socket.gethostname()}"
        return self.put_object_content(filename, content.encode("utf-8"))


# ------------------------------------------------------------------------------
# Dependency Provider (FastAPI Depends)
# ------------------------------------------------------------------------------
_s3_service: S3Service | None = None


def get_s3_service() -> S3Service:
    """Returns a singleton S3Service instance for FastAPI dependency injection."""
    global _s3_service
    if _s3_service is None:
        _s3_service = S3Service()
    return _s3_service


# Module-level aliases for backwards compatibility
def ensure_bucket_exists() -> None:
    return get_s3_service().ensure_bucket_exists()


def list_bucket_objects() -> dict:
    return get_s3_service().list_bucket_objects()


def get_object_content(key: str) -> tuple[bytes, str]:
    return get_s3_service().get_object_content(key)


def delete_object(key: str) -> None:
    return get_s3_service().delete_object(key)


def put_object_content(key: str, content: bytes, content_type: str = "application/octet-stream") -> dict:
    return get_s3_service().put_object_content(key, content, content_type)


def upload_sample_document(filename: str = "sample_report.txt") -> dict:
    return get_s3_service().upload_sample_document(filename)
