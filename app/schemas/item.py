from typing import List

from pydantic import BaseModel, ConfigDict, Field

# Largest value NUMERIC(10, 2) can hold; anything above overflows in Postgres
MAX_PRICE = 99_999_999.99


class ItemBase(BaseModel):
    # Bounds mirror the items table: name VARCHAR(100), price NUMERIC(10, 2)
    name: str = Field(max_length=100)
    price: float = Field(
        gt=0,
        le=MAX_PRICE,
        description="Price must be greater than 0 and at most 99999999.99",
    )
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
