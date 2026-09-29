import socket

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.api.deps import DbPoolDep, RedisDep
from app.schemas.item import ItemCreate, ItemCreateResponse, ItemResponse, ItemsListResponse
from app.services import items as items_service
from app.services.email import send_mock_email

router = APIRouter()


@router.post("", status_code=201, response_model=ItemCreateResponse)
async def create_item(
    item: ItemCreate,
    background_tasks: BackgroundTasks,
    pool: DbPoolDep,
    redis_client: RedisDep,
):
    """WRITE to database, invalidate cache, and send mock email in background."""
    async with pool.acquire() as conn:
        created = await items_service.create_item(conn, redis_client, item)
        background_tasks.add_task(send_mock_email, item.name, float(item.price))
        return {
            "status": "created",
            "item": created,
            "container_id": socket.gethostname(),
        }


@router.get("", response_model=ItemsListResponse)
async def get_items(
    pool: DbPoolDep,
    redis_client: RedisDep,
    limit: int = 10,
):
    """READ with Redis Cache-Aside pattern."""
    return await items_service.get_items(pool, redis_client, limit)


@router.get("/{item_id}", response_model=ItemResponse)
async def get_item(
    item_id: int,
    pool: DbPoolDep,
    redis_client: RedisDep,
):
    """READ single item with Redis Cache-Aside pattern."""
    item = await items_service.get_item_by_id(pool, redis_client, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item
