from typing import Literal

from pydantic import BaseModel, Field

GarmentZone = Literal["upper_body", "lower_body", "one_piece", "accessory", "other"]
Audience = Literal["men", "women", "unisex"]


class QueryDraft(BaseModel):
    id: str
    text: str
    garment_zone: GarmentZone
    rationale: str
    selected: bool = True


class PlanRequest(BaseModel):
    user_input: str = Field(min_length=2, max_length=1000)
    user_key: str = Field(default="demo-user", min_length=1, max_length=120)
    audience: Audience | None = None


class PlanResponse(BaseModel):
    original_input: str
    queries: list[QueryDraft]
    planner: str
    audience: Audience | None = None
    knowledge_observation_ids: list[str] = Field(default_factory=list)
    planning_note: str = ""


class RefineRequest(PlanRequest):
    existing_queries: list[QueryDraft] = Field(default_factory=list)
    original_input: str = Field(default="", max_length=1000)


class SearchRequest(BaseModel):
    queries: list[QueryDraft]
    top_k: int = Field(default=25, ge=1, le=30)
    user_key: str = Field(default="demo-user", min_length=1, max_length=120)
    user_input: str = Field(default="", max_length=1200)
    audience: Audience | None = None
    shortlist_count: int = Field(default=15, ge=5, le=30)
    final_count: int = Field(default=5, ge=1, le=10)
    use_aesthetic_review: bool = True


class ClothResult(BaseModel):
    id: int
    source_item_id: int | None
    product_display_name: str
    garment_zone: GarmentZone
    image_url: str
    price: int
    original_price: int | None = None
    discounted_price: int | None = None
    currency: str = "INR"
    brand_name: str | None = None
    age_group: str | None = None
    gender: str | None = None
    usage: str | None = None
    base_colour: str | None
    article_type: str | None
    similarity: float
    image_path: str | None = Field(default=None, exclude=True, repr=False)


class QuerySearchResult(BaseModel):
    query: QueryDraft
    clothes: list[ClothResult]


class SearchResponse(BaseModel):
    results: list[QuerySearchResult]
    model: str


class OutfitScoreBreakdown(BaseModel):
    fashion_clip: float = Field(ge=0, le=1)
    compatibility: float = Field(ge=0, le=1)
    context_fit: float = Field(ge=0, le=1)
    preference_adjustment: float
    aesthetic: float | None = Field(default=None, ge=0, le=1)


class AestheticReview(BaseModel):
    occasion_fit: int = Field(ge=0, le=100)
    color_harmony: int = Field(ge=0, le=100)
    silhouette_balance: int = Field(ge=0, le=100)
    material_coherence: int = Field(ge=0, le=100)
    overall_aesthetic: int = Field(ge=0, le=100)
    fatal_issues: list[str] = Field(default_factory=list)
    reason: str


class OutfitRecommendation(BaseModel):
    id: str
    kind: Literal["separates", "one_piece"]
    items: list[ClothResult]
    score: float
    reasons: list[str]
    score_breakdown: OutfitScoreBreakdown | None = None
    aesthetic_review: AestheticReview | None = None


class RecommendationResponse(BaseModel):
    recommendations: list[OutfitRecommendation]
    aesthetic_reviewed: bool = False
    review_note: str = ""
    knowledge_observation_count: int = 0
    knowledge_sources: list[str] = Field(default_factory=list)
    knowledge_note: str = ""


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
    original_price: int | None = None
    discounted_price: int | None = None
    currency: str = "INR"
    brand_name: str | None = None
    age_group: str | None = None
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
