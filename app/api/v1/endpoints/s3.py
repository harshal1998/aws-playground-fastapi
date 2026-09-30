from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request, Response
from starlette.concurrency import run_in_threadpool

from app.api.deps import S3ServiceDep
from app.core.config import settings
from app.schemas.s3 import TextUploadRequest

router = APIRouter()


def _content_disposition(key: str) -> str:
    """Builds an attachment Content-Disposition header that is safe for any key.

    filename= gets an ASCII-only fallback (non-ASCII, control characters,
    quotes and backslashes replaced by "_"); the exact name goes in the
    RFC 5987 filename* parameter.
    """
    name = key.rsplit("/", 1)[-1] or "download"
    fallback = "".join(c if " " <= c <= "~" and c not in '"\\' else "_" for c in name)
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(name, safe='')}"


def _upload_too_large() -> HTTPException:
    """413 error for uploads over S3_MAX_UPLOAD_BYTES."""
    return HTTPException(status_code=413, detail=f"Upload exceeds the {settings.S3_MAX_UPLOAD_BYTES} byte limit")


@router.get("/objects")
def list_s3_objects(s3_service: S3ServiceDep):
    """Lists all stored documents in the LocalStack S3 bucket."""
    return s3_service.list_bucket_objects()


@router.get("/file")
def get_s3_file(key: str, s3_service: S3ServiceDep):
    """Downloads the content of an S3 object as a file attachment."""
    content, content_type = s3_service.get_object_content(key)
    # Never render uploaded content inline: an uploaded HTML/SVG file would
    # otherwise run scripts on the portal's origin.
    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Content-Disposition": _content_disposition(key),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/file")
def delete_s3_file(key: str, s3_service: S3ServiceDep):
    """Deletes an object from the S3 bucket."""
    s3_service.delete_object(key)
    return {"status": "deleted", "key": key}


@router.post("/upload")
async def upload_file_to_s3(
    request: Request,
    s3_service: S3ServiceDep,
    filename: str = Query(...),
):
    """Uploads any binary or text file (up to S3_MAX_UPLOAD_BYTES) to the LocalStack S3 bucket."""
    max_bytes = settings.S3_MAX_UPLOAD_BYTES
    too_large = _upload_too_large()

    # Reject early on the declared size, then count bytes while streaming so a
    # chunked or mis-declared body can't buffer more than the limit in memory.
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > max_bytes:
        raise too_large

    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > max_bytes:
            raise too_large

    content_type = request.headers.get("content-type", "application/octet-stream")
    # boto3 is blocking: run it in the threadpool so the event loop keeps serving.
    return await run_in_threadpool(
        s3_service.put_object_content, filename, bytes(body), content_type=content_type
    )


@router.post("/upload-text")
def upload_text_file(
    payload: TextUploadRequest,
    s3_service: S3ServiceDep,
):
    """Uploads a custom text document (up to S3_MAX_UPLOAD_BYTES once encoded) to the S3 bucket."""
    content = payload.content.encode("utf-8")
    if len(content) > settings.S3_MAX_UPLOAD_BYTES:
        raise _upload_too_large()
    return s3_service.put_object_content(payload.filename, content)


@router.post("/upload-sample")
def upload_sample_to_s3(
    s3_service: S3ServiceDep,
    filename: str = "sample_report.txt",
):
    """Demonstrates uploading to local AWS S3 via LocalStack."""
    return s3_service.upload_sample_document(filename)
