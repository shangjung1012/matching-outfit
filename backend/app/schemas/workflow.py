from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

GarmentZone = Literal["upper_body", "lower_body", "one_piece", "accessory", "other"]
Audience = Literal["men", "women", "unisex"]
RequirementField = Literal[
    "occasion", "time", "context", "special_requirements", "additional_notes"
]


class ReferenceLink(BaseModel):
    title: str
    url: str


class QueryDraft(BaseModel):
    id: str
    text: str
    garment_zone: GarmentZone
    rationale: str
    selected: bool = True
    knowledge_observation_ids: list[str] = Field(default_factory=list)
    references: list[ReferenceLink] = Field(default_factory=list)


class PlanRequest(BaseModel):
    user_input: str = Field(min_length=2, max_length=1000)
    user_key: str = Field(default="demo-user", min_length=1, max_length=120)
    audience: Audience | None = None


class ChatTurn(BaseModel):
    role: Literal["agent", "user"]
    text: str = Field(min_length=1, max_length=2000)


class RequirementSummary(BaseModel):
    occasion: str = ""
    time: str = ""
    context: str = ""
    special_requirements: str = ""
    additional_notes: str = ""
    search_brief: str = ""


class ClarificationRequest(BaseModel):
    messages: list[ChatTurn] = Field(min_length=1, max_length=30)
    user_key: str = Field(default="demo-user", min_length=1, max_length=120)
    audience: Audience | None = None


class ClarificationResponse(BaseModel):
    reply: str
    requirements: RequirementSummary
    missing_fields: list[RequirementField] = Field(default_factory=list)
    ready_to_plan: bool = False


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
    references: list[ReferenceLink] = Field(default_factory=list)
    image_path: str | None = Field(default=None, exclude=True, repr=False)


class QuerySearchResult(BaseModel):
    query: QueryDraft
    clothes: list[ClothResult]
    relaxed: bool = False  # the user's "avoid" hard rules emptied this zone, so they were dropped here


class SearchResponse(BaseModel):
    results: list[QuerySearchResult]
    model: str


class OutfitScoreBreakdown(BaseModel):
    fashion_clip: float = Field(ge=0, le=1)
    compatibility: float = Field(ge=0, le=1)
    context_fit: float = Field(ge=0, le=1)
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
    references: list[ReferenceLink] = Field(default_factory=list)
    score_breakdown: OutfitScoreBreakdown | None = None
    aesthetic_review: AestheticReview | None = None


class RecommendationResponse(BaseModel):
    recommendations: list[OutfitRecommendation]
    aesthetic_reviewed: bool = False
    review_note: str = ""
    knowledge_observation_count: int = 0
    knowledge_sources: list[str] = Field(default_factory=list)
    knowledge_note: str = ""


# ---------------------------------------------------------------------------
# User preferences
#
# Hard rules live on the ``user_hard_rules`` row and act as gates - they are
# translated into SQL filters on ``clothes``. Soft preferences are context-scoped
# sentences authored by the user or confirmed from liked outfits. They guide LLM
# stages but never alter rank scores directly.
# ---------------------------------------------------------------------------

PreferenceSource = Literal["explicit", "implicit"]


class HardRules(BaseModel):
    price_min: int | None = Field(default=None, ge=0)
    price_max: int | None = Field(default=None, ge=0)
    avoid_colours: list[str] = Field(default_factory=list)
    avoid_article_types: list[str] = Field(default_factory=list)
    avoid_master_categories: list[str] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _price_order(self) -> "HardRules":
        if (
            self.price_min is not None
            and self.price_max is not None
            and self.price_min > self.price_max
        ):
            raise ValueError("price_min must not exceed price_max")
        return self


class HardRulesView(HardRules):
    user_key: str

    model_config = ConfigDict(from_attributes=True)


class HardRulesUpdate(HardRules):
    user_key: str = Field(min_length=1, max_length=120)


class StylePreferenceBase(BaseModel):
    preference_text: str = Field(min_length=1, max_length=500)
    context_occasions: list[str] = Field(default_factory=list)
    context_times: list[str] = Field(default_factory=list)
    context_situations: list[str] = Field(default_factory=list)


class StylePreferenceCreate(StylePreferenceBase):
    source: PreferenceSource = "explicit"
    origin_item_ids: list[str] = Field(default_factory=list)


class StylePreferencePatch(BaseModel):
    is_active: bool | None = None
    preference_text: str | None = Field(default=None, min_length=1, max_length=500)


class StylePreferenceView(StylePreferenceCreate):
    id: int
    user_key: str
    is_active: bool = True
    confirmed_at: datetime | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class PreferenceBundle(BaseModel):
    hard: HardRulesView
    soft: list[StylePreferenceView] = Field(default_factory=list)


class StylePreferenceProposalRequest(BaseModel):
    user_key: str = Field(default="demo-user", min_length=1, max_length=120)
    user_request: str = Field(min_length=2, max_length=1200)
    outfit_item_ids: list[list[int]] = Field(min_length=1)
    occasion: str = Field(default="", max_length=300)
    time: str = Field(default="", max_length=300)
    context: str = Field(default="", max_length=500)


class StylePreferenceProposal(BaseModel):
    proposals: list[StylePreferenceCreate] = Field(default_factory=list)
    explanation: str = "Only a proposal - persist it after the user confirms."


class StylePreferenceConfirmRequest(BaseModel):
    user_key: str = Field(default="demo-user", min_length=1, max_length=120)
    rows: list[StylePreferenceCreate] = Field(min_length=1)


class StylePreferenceMutationResponse(BaseModel):
    status: str
    user_key: str
    created: int = 0
    updated: int = 0
    removed: int = 0


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

