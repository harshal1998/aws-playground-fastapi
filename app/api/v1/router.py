from fastapi import APIRouter

from app.api.v1.endpoints import aws, items, root, s3

api_router = APIRouter()
api_router.include_router(root.router, tags=["Health & Status"])
api_router.include_router(items.router, prefix="/items", tags=["Items"])
api_router.include_router(s3.router, prefix="/s3", tags=["LocalStack S3"])
api_router.include_router(aws.router, prefix="/aws", tags=["LocalStack AWS Services"])

