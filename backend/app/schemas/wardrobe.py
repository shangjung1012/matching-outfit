from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


WardrobeCategory = Literal["upper_body", "lower_body", "one_piece", "shoes", "bags"]


class WardrobeItemView(BaseModel):
    id: int
    name: str
    category: WardrobeCategory
    image_url: str
    original_filename: str
    is_favorite: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WardrobeFavoriteUpdate(BaseModel):
    is_favorite: bool
