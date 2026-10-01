"""S3Service against moto's in-memory S3."""

import pytest
from botocore.exceptions import ClientError


def test_ensure_bucket_exists_creates_bucket_and_is_idempotent(s3_service):
    """Verify startup creates the bucket and a second call is harmless."""
    s3_service.ensure_bucket_exists()
    s3_service.ensure_bucket_exists()
    names = [b["Name"] for b in s3_service.client.list_buckets()["Buckets"]]
    assert names == [s3_service.bucket_name]


def test_bucket_is_created_lazily_on_first_use(s3_service):
    """Verify an operation creates the bucket when startup never did."""
    assert s3_service.list_bucket_objects() == {"bucket": s3_service.bucket_name, "count": 0, "objects": []}


def test_put_and_get_round_trip(s3_service):
    """Verify uploaded bytes and content type come back unchanged."""
    result = s3_service.put_object_content("docs/a.json", b'{"a": 1}', "application/json")
    assert result["size_bytes"] == 8
    content, content_type = s3_service.get_object_content("docs/a.json")
    assert content == b'{"a": 1}'
    assert content_type == "application/json"


def test_list_follows_every_page(s3_service):
    """Verify listing follows ContinuationToken across pages."""
    for i in range(5):
        s3_service.put_object_content(f"obj-{i}", b"x" * i)

    # Force 2 keys per page (instead of 1000) so pagination is exercised.
    real_list = s3_service.client.list_objects_v2
    calls = []

    def small_pages(**kwargs):
        calls.append(kwargs)
        return real_list(MaxKeys=2, **kwargs)

    s3_service.client.list_objects_v2 = small_pages
    listing = s3_service.list_bucket_objects()

    assert listing["count"] == 5
    assert sorted(o["key"] for o in listing["objects"]) == [f"obj-{i}" for i in range(5)]
    assert {o["key"]: o["size_bytes"] for o in listing["objects"]}["obj-4"] == 4
    assert len(calls) == 3
    assert "ContinuationToken" in calls[1]


def test_delete_removes_object(s3_service):
    """Verify a deleted object is gone from listings and reads."""
    s3_service.put_object_content("gone.txt", b"bye")
    s3_service.delete_object("gone.txt")
    assert s3_service.list_bucket_objects()["count"] == 0
    with pytest.raises(ClientError) as exc:
        s3_service.get_object_content("gone.txt")
    assert exc.value.response["Error"]["Code"] == "NoSuchKey"


def test_bucket_recreated_after_it_disappears(s3_service):
    """Verify NoSuchBucket (e.g. LocalStack restarted) recreates the bucket and retries."""
    s3_service.put_object_content("a.txt", b"a")
    s3_service.delete_object("a.txt")
    s3_service.client.delete_bucket(Bucket=s3_service.bucket_name)
    s3_service.put_object_content("b.txt", b"b")
    assert [o["key"] for o in s3_service.list_bucket_objects()["objects"]] == ["b.txt"]
