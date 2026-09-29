from botocore.exceptions import ClientError
from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.api.deps import S3ServiceDep
from app.schemas.s3 import TextUploadRequest

router = APIRouter()


@router.get("/objects")
def list_s3_objects(s3_service: S3ServiceDep):
    """Lists all stored documents in the LocalStack S3 bucket."""
    return s3_service.list_bucket_objects()


@router.get("/file")
def get_s3_file(key: str, s3_service: S3ServiceDep):
    """Downloads or views the content of an S3 object."""
    try:
        content, content_type = s3_service.get_object_content(key)
        return Response(
            content=content,
            media_type=content_type,
            headers={"Content-Disposition": f'inline; filename="{key}"'},
        )
    except ClientError as e:
        raise HTTPException(status_code=404, detail="File not found in S3 bucket") from e


@router.delete("/file")
def delete_s3_file(key: str, s3_service: S3ServiceDep):
    """Deletes an object from the S3 bucket."""
    try:
        s3_service.delete_object(key)
        return {"status": "deleted", "key": key}
    except ClientError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/upload")
async def upload_file_to_s3(
    request: Request,
    s3_service: S3ServiceDep,
    filename: str = Query(...),
):
    """Uploads any binary or text file to the LocalStack S3 bucket."""
    content = await request.body()
    content_type = request.headers.get("content-type", "application/octet-stream")
    return s3_service.put_object_content(filename, content, content_type=content_type)


@router.post("/upload-text")
def upload_text_file(
    payload: TextUploadRequest,
    s3_service: S3ServiceDep,
):
    """Uploads a custom text document to the S3 bucket."""
    return s3_service.put_object_content(payload.filename, payload.content.encode("utf-8"))


@router.post("/upload-sample")
def upload_sample_to_s3(
    s3_service: S3ServiceDep,
    filename: str = "sample_report.txt",
):
    """Demonstrates uploading to local AWS S3 via LocalStack."""
    return s3_service.upload_sample_document(filename)
