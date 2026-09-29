from typing import List

from pydantic import BaseModel, ConfigDict, Field


class ItemBase(BaseModel):
    name: str
    price: float = Field(gt=0, description="Price must be greater than 0")
    is_offer: bool = False


class ItemCreate(ItemBase):
    pass


class ItemResponse(ItemBase):
    id: int
    created_at: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ItemCreateResponse(BaseModel):
    status: str = "created"
    item: ItemResponse
    container_id: str


class ItemsListResponse(BaseModel):
    source: str
    count: int
    items: List[ItemResponse]
    container_id: str
