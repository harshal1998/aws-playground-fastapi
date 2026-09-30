"""
S3 Storage Integration for LocalStack/AWS.
Provides a class-based S3Service managing buckets and object storage.
"""
import socket
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

    def ensure_bucket_exists(self) -> None:
        """Ensures the default S3 bucket exists in LocalStack on startup."""
        try:
            self.client.create_bucket(Bucket=self.bucket_name)
            print(f"Successfully initialized LocalStack S3 bucket: {self.bucket_name}")
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                print(f"Notice during S3 bucket initialization: {e}")
        except (BotoCoreError, OSError) as e:
            # EndpointConnectionError and botocore timeouts derive from
            # BotoCoreError, not OSError; never let them crash startup.
            print(f"LocalStack S3 connection skipped (service may be offline): {e}")

    def list_bucket_objects(self) -> dict:
        """Lists all objects in the configured S3 bucket."""
        self.ensure_bucket_exists()
        response = self.client.list_objects_v2(Bucket=self.bucket_name)
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
        self.ensure_bucket_exists()
        obj = self.client.get_object(Bucket=self.bucket_name, Key=key)
        content = obj["Body"].read()
        content_type = obj.get("ContentType", "application/octet-stream")
        return content, content_type

    def delete_object(self, key: str) -> None:
        """Deletes an object from the S3 bucket."""
        self.ensure_bucket_exists()
        self.client.delete_object(Bucket=self.bucket_name, Key=key)

    def put_object_content(
        self,
        key: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> dict:
        """Puts arbitrary byte content into S3 under the given key."""
        self.ensure_bucket_exists()
        self.client.put_object(Bucket=self.bucket_name, Key=key, Body=content, ContentType=content_type)
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
