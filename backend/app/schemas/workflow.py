from typing import Literal

from pydantic import BaseModel, Field

GarmentZone = Literal["upper_body", "lower_body", "one_piece", "accessory", "other"]


class QueryDraft(BaseModel):
    id: str
    text: str
    garment_zone: GarmentZone
    rationale: str
    selected: bool = True


class PlanRequest(BaseModel):
    user_input: str = Field(min_length=2, max_length=1000)
    user_key: str = Field(default="demo-user", min_length=1, max_length=120)


class PlanResponse(BaseModel):
    original_input: str
    queries: list[QueryDraft]
    planner: str


class RefineRequest(PlanRequest):
    existing_queries: list[QueryDraft] = Field(default_factory=list)


class SearchRequest(BaseModel):
    queries: list[QueryDraft]
    top_k: int = Field(default=6, ge=1, le=30)
    user_key: str = Field(default="demo-user", min_length=1, max_length=120)


class ClothResult(BaseModel):
    id: int
    source_item_id: int | None
    product_display_name: str
    garment_zone: GarmentZone
    image_url: str
    price: int
    base_colour: str | None
    article_type: str | None
    similarity: float


class QuerySearchResult(BaseModel):
    query: QueryDraft
    clothes: list[ClothResult]


class SearchResponse(BaseModel):
    results: list[QuerySearchResult]
    model: str


class OutfitRecommendation(BaseModel):
    id: str
    kind: Literal["separates", "one_piece"]
    items: list[ClothResult]
    score: float
    reasons: list[str]


class RecommendationResponse(BaseModel):
    recommendations: list[OutfitRecommendation]


class PreferenceProposalRequest(BaseModel):
    user_key: str = Field(default="demo-user", min_length=1, max_length=120)
    liked_item_ids: list[int] = Field(min_length=1)


class PreferenceProposal(BaseModel):
    favorite_colors_to_add: list[str]
    favorite_article_types_to_add: list[str]
    explanation: str


class PreferenceConfirmation(BaseModel):
    user_key: str = Field(default="demo-user", min_length=1, max_length=120)
    favorite_colors_to_add: list[str] = Field(default_factory=list)
    favorite_article_types_to_add: list[str] = Field(default_factory=list)


class PreferenceConfirmationResponse(BaseModel):
    status: str
    user_key: str


class CatalogItem(BaseModel):
    id: int
    source_item_id: int | None
    product_display_name: str
    garment_zone: GarmentZone
    image_url: str
    price: int
    gender: str | None
    master_category: str | None
    sub_category: str | None
    article_type: str | None
    base_colour: str | None
    season: str | None
    year: int | None
    usage: str | None
    has_embedding: bool


class CatalogResponse(BaseModel):
    items: list[CatalogItem]
    total: int


class UserPreferenceView(BaseModel):
    user_key: str
    favorite_colors: list[str] = Field(default_factory=list)
    disliked_colors: list[str] = Field(default_factory=list)
    preferred_price_min: int | None = None
    preferred_price_max: int | None = None
    preferred_styles: list[str] = Field(default_factory=list)
    preferred_categories: list[str] = Field(default_factory=list)
    preferred_usages: list[str] = Field(default_factory=list)
    favorite_article_types: list[str] = Field(default_factory=list)
    disliked_article_types: list[str] = Field(default_factory=list)
    notes: str | None = None


class UserPreferenceUpdate(UserPreferenceView):
    pass
