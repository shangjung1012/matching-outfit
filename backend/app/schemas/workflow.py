from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.fashion_knowledge import OutfitObservation

GarmentZone = Literal["upper_body", "lower_body", "one_piece", "accessory", "other"]
PlannerGarmentZone = Literal["upper_body", "lower_body", "one_piece"]
Audience = Literal["men", "women", "unisex"]
RequirementField = Literal[
    "location",
    "target_date",
    "outfit_budget_max",
    "occasions",
    "seasons",
    "times_of_day",
    "climates",
    "formalities",
    "activities",
    "styles",
    "special_requirements",
    "additional_notes",
]


class ReferenceLink(BaseModel):
    title: str
    url: str


class OccasionInterpretation(BaseModel):
    social_context: str = Field(min_length=2, max_length=300)
    formality_target: float = Field(ge=0, le=1)
    visual_impact: Literal["low", "medium", "high"]
    practicality: Literal["low", "medium", "high"]

    model_config = ConfigDict(extra="forbid")


class StylingConcept(BaseModel):
    direction_id: str = Field(min_length=1, max_length=1)
    concept_name: str = Field(min_length=2, max_length=120)
    outfit_formula: str = Field(min_length=3, max_length=400)
    upper_role: str | None = Field(default=None, max_length=300)
    lower_role: str | None = Field(default=None, max_length=300)
    one_piece_role: str | None = Field(default=None, max_length=300)
    visible_cues: list[str] = Field(min_length=1, max_length=10)
    balance_rules: list[str] = Field(min_length=1, max_length=8)

    model_config = ConfigDict(extra="forbid")


class BodyContext(BaseModel):
    height_band: Literal["short", "average", "tall", "unknown"] = "unknown"
    bmi_band: Literal["lower", "middle", "higher", "unknown"] = "unknown"
    frame_scale: Literal["small", "medium", "large", "unknown"] = "unknown"
    shoulder_hip_balance: Literal["shoulder_dominant", "balanced", "hip_dominant", "unknown"] = "unknown"
    midsection_fullness: Literal["lower", "moderate", "higher", "unknown"] = "unknown"
    upper_body_volume: Literal["lower", "moderate", "higher", "unknown"] = "unknown"
    lower_body_volume: Literal["lower", "moderate", "higher", "unknown"] = "unknown"
    thigh_or_calf_volume: Literal["lower", "moderate", "higher", "unknown"] = "unknown"
    leg_torso_ratio: Literal["shorter_legs", "balanced", "longer_legs", "unknown"] = "unknown"
    fit_preference: Literal["fitted", "regular", "relaxed", "oversized", "mixed", "unknown"] = "unknown"
    exposure_preference: Literal["low", "medium", "high", "unknown"] = "unknown"
    areas_to_emphasize: list[str] = Field(default_factory=list, max_length=12)
    areas_not_to_emphasize: list[str] = Field(default_factory=list, max_length=12)
    access_needs: list[str] = Field(default_factory=list, max_length=12)
    confidence: Literal["high", "medium", "low"] = "low"

    model_config = ConfigDict(extra="forbid")


class BodyStrategy(BaseModel):
    confidence: Literal["low", "medium", "high"] = "low"
    fit_direction: list[str] = Field(default_factory=list, max_length=12)
    proportion_direction: list[str] = Field(default_factory=list, max_length=12)
    exposure_direction: list[str] = Field(default_factory=list, max_length=12)
    movement_and_access_direction: list[str] = Field(default_factory=list, max_length=12)
    soft_biases: list[str] = Field(default_factory=list, max_length=12)
    hard_constraints: list[str] = Field(default_factory=list, max_length=12)
    unknowns: list[str] = Field(default_factory=list, max_length=20)

    model_config = ConfigDict(extra="forbid")


class ActivityContext(BaseModel):
    activity: str = ""
    activity_present: bool = False
    activity_mode: Literal["appearance_dominant", "balanced", "function_dominant", "not_applicable"] = "not_applicable"
    appearance_priority: Literal["low", "medium", "high"] = "low"
    requested_visual_identity: str = ""
    explicit_functional_requests: list[str] = Field(default_factory=list, max_length=12)
    avoid_style_drift: list[str] = Field(default_factory=list, max_length=12)
    primary_goal: str = ""
    secondary_goal: str = ""
    functional_priority: Literal["low", "medium", "high"] = "low"
    minimum_functional_requirements: list[str] = Field(default_factory=list, max_length=12)
    avoid_functional_drift: list[str] = Field(default_factory=list, max_length=12)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy(cls, value):
        if not isinstance(value, dict):
            return value
        result = dict(value)
        legacy = result.get("activity_mode")
        mapping = {
            "appearance_led_performance": ("appearance_dominant", "high", "low"),
            "functional_training": ("function_dominant", "low", "high"),
            "mixed": ("balanced", "high", "high"),
            "ordinary_occasion": ("not_applicable", "low", "low"),
        }
        if legacy in mapping:
            mode, appearance, function = mapping[legacy]
            result["activity_mode"] = mode
            result.setdefault("appearance_priority", appearance)
            result.setdefault("functional_priority", function)
            result.setdefault("activity_present", mode != "not_applicable")
        result.setdefault("requested_visual_identity", result.get("primary_goal", ""))
        result.setdefault("avoid_style_drift", result.get("avoid_functional_drift", []))
        return result

    @model_validator(mode="after")
    def summarize_priorities(self):
        if not self.activity_present:
            self.activity_mode = "not_applicable"
        else:
            priorities = {"low": 0, "medium": 1, "high": 2}
            appearance = priorities[self.appearance_priority]
            function = priorities[self.functional_priority]
            self.activity_mode = "appearance_dominant" if appearance > function else "function_dominant" if function > appearance else "balanced"
        return self


class FashionIntent(BaseModel):
    activity_context: ActivityContext = Field(default_factory=ActivityContext)
    forbidden_style_drift: list[str] = Field(default_factory=list, max_length=16)
    body_context: BodyContext = Field(default_factory=BodyContext)
    body_strategy: BodyStrategy = Field(default_factory=BodyStrategy)
    user_goal: str = Field(min_length=3, max_length=500)
    desired_impression: list[str] = Field(min_length=1, max_length=10)
    occasion_interpretation: OccasionInterpretation
    core_aesthetic: list[str] = Field(min_length=1, max_length=10)
    must_have_visual_cues: list[str] = Field(min_length=1, max_length=12)
    optional_visual_cues: list[str] = Field(default_factory=list, max_length=12)
    avoid_concepts: list[str] = Field(default_factory=list, max_length=12)
    styling_principles: list[str] = Field(min_length=1, max_length=12)
    concepts: list[StylingConcept] = Field(min_length=7, max_length=7)
    ambiguities: list[str] = Field(default_factory=list, max_length=8)
    confidence: float = Field(ge=0, le=1)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _validate_concept_contract(self) -> "FashionIntent":
        by_id = {concept.direction_id: concept for concept in self.concepts}
        expected = set("ABCDEFG")
        if len(by_id) != 7 or set(by_id) != expected:
            raise ValueError("FashionIntent concepts must have unique direction IDs A-G")
        for direction_id in "ABCDE":
            concept = by_id[direction_id]
            if not concept.upper_role or not concept.lower_role:
                raise ValueError(f"Direction {direction_id} requires upper_role and lower_role")
        for direction_id in "FG":
            if not by_id[direction_id].one_piece_role:
                raise ValueError(f"Direction {direction_id} requires one_piece_role")
        return self


class PairingDirection(BaseModel):
    id: str = Field(min_length=1, max_length=24)
    concept: str = Field(min_length=2, max_length=300)
    upper_body_focus: str = Field(min_length=2, max_length=300)
    lower_body_focus: str = Field(min_length=2, max_length=300)
    color_relationship: str = Field(min_length=2, max_length=300)


class StylingGuide(BaseModel):
    concept: str = Field(min_length=2, max_length=500)
    desired_impression: list[str] = Field(default_factory=list, max_length=10)
    visual_attributes: list[str] = Field(default_factory=list, max_length=12)
    avoid_misinterpretations: list[str] = Field(default_factory=list, max_length=12)
    color_direction: list[str] = Field(default_factory=list, max_length=12)
    silhouette_direction: list[str] = Field(default_factory=list, max_length=12)
    material_direction: list[str] = Field(default_factory=list, max_length=12)
    pattern_direction: list[str] = Field(default_factory=list, max_length=12)
    pairing_directions: list[PairingDirection] = Field(default_factory=list, max_length=7)
    styling_principles: list[str] = Field(default_factory=list, max_length=12)
    reviewer_checklist: list[str] = Field(default_factory=list, max_length=12)


class QueryDraft(BaseModel):
    id: str
    text: str
    garment_zone: GarmentZone
    rationale: str
    direction_id: str | None = Field(default=None, max_length=24)
    selected: bool = True
    knowledge_observation_ids: list[str] = Field(default_factory=list)
    references: list[ReferenceLink] = Field(default_factory=list)


class ShoeSpec(BaseModel):
    """A conservative, retrieval-ready shoe brief produced by Query Planner."""

    shoe_type: str = Field(default="", max_length=80)
    shoe_color: str = Field(default="", max_length=80)
    shoe_query: str = Field(default="", max_length=240)
    material_appearance: str = Field(default="", max_length=80)
    profile: str = Field(default="", max_length=80)


class DirectionShoePlan(BaseModel):
    """One shoe retrieval brief shared by outfits from the same A-G direction."""

    direction_id: str = Field(min_length=1, max_length=24)
    shoe_spec: ShoeSpec


class ChatTurn(BaseModel):
    role: Literal["agent", "user"]
    text: str = Field(min_length=1, max_length=2000)


class WeatherContext(BaseModel):
    status: Literal["available", "unavailable"] = "unavailable"
    location: str = ""
    target_date: str = ""
    location_assumed: bool = False
    temperature_min_c: float | None = None
    temperature_max_c: float | None = None
    apparent_temperature_min_c: float | None = None
    apparent_temperature_max_c: float | None = None
    precipitation_probability_max: float | None = None
    source_url: str = "https://open-meteo.com/"
    fetched_at: str = ""
    note: str = ""


class RequirementSummary(BaseModel):
    weather: WeatherContext | None = None
    location: str = ""
    target_date: str = ""
    # A per-request cap for the combined price of one recommended outfit.
    # This is intentionally distinct from saved per-item price preferences.
    outfit_budget_max: float | None = Field(default=None, ge=0)
    defaulted_fields: list[str] = Field(default_factory=list)
    occasions: list[str] = Field(default_factory=list)
    seasons: list[str] = Field(default_factory=list)
    times_of_day: list[str] = Field(default_factory=list)
    climates: list[str] = Field(default_factory=list)
    formalities: list[str] = Field(default_factory=list)
    activities: list[str] = Field(default_factory=list)
    styles: list[str] = Field(default_factory=list)
    special_requirements: list[str] = Field(default_factory=list)
    additional_notes: str = ""
    search_brief: str = ""
    tag_translations: dict[str, str] = Field(default_factory=dict)


class GeneratedQueryTrace(BaseModel):
    garment_zone: Literal["upper_body", "lower_body", "one_piece"]
    direction_id: str
    text: str
    rationale: str


class QueryNormalizationChange(BaseModel):
    direction_id: str | None = None
    garment_zone: GarmentZone
    before: str
    after: str


class QueryPlanDebug(BaseModel):
    knowledge_observations: list[OutfitObservation] = Field(default_factory=list)
    knowledge_used_ids: list[str] = Field(default_factory=list)
    knowledge_gaps: list[str] = Field(default_factory=list)
    knowledge_note: str = ""
    raw_user_text: str
    requirement_summary: RequirementSummary | None = None
    fashion_intent: FashionIntent | None = None
    generated_queries_before_normalization: list[GeneratedQueryTrace] = Field(
        default_factory=list
    )
    generated_queries_after_normalization: list[QueryDraft] = Field(default_factory=list)
    shoe_plans: list[DirectionShoePlan] = Field(default_factory=list)
    normalizer_changes: list[QueryNormalizationChange] = Field(default_factory=list)
    query_warnings: list[str] = Field(default_factory=list)
    intent_fallback_used: bool = False
    intent_fallback_error: str = ""
    model: str
    prompt_version: str
    stage_timings_ms: dict[str, float] = Field(default_factory=dict)


class PlanRequest(BaseModel):
    user_input: str = Field(min_length=2, max_length=1000)
    user_key: str = Field(default="demo-user", min_length=1, max_length=120)
    audience: Audience | None = None
    requirements: RequirementSummary | None = None
    # The catalog zones this plan is allowed to retrieve. None keeps the default full outfit plan.
    search_garment_zones: list[PlannerGarmentZone] | None = Field(default=None, min_length=1, max_length=3)
    include_debug: bool = False


class ClarificationRequest(BaseModel):
    messages: list[ChatTurn] = Field(min_length=1, max_length=30)
    user_key: str = Field(default="demo-user", min_length=1, max_length=120)
    audience: Audience | None = None
    previous_requirements: RequirementSummary | None = None


class ClarificationResponse(BaseModel):
    reply: str
    requirements: RequirementSummary
    missing_fields: list[RequirementField] = Field(default_factory=list)
    ready_to_plan: bool = False


class PlanResponse(BaseModel):
    knowledge_observations: list[OutfitObservation] = Field(default_factory=list)
    knowledge_gaps: list[str] = Field(default_factory=list)
    knowledge_note: str = ""
    original_input: str
    queries: list[QueryDraft]
    shoe_plans: list[DirectionShoePlan] = Field(default_factory=list)
    planner: str
    audience: Audience | None = None
    knowledge_observation_ids: list[str] = Field(default_factory=list)
    planning_note: str = ""
    styling_guide: StylingGuide | None = None
    fashion_intent: FashionIntent | None = None
    debug: QueryPlanDebug | None = None


class RefineRequest(PlanRequest):
    existing_queries: list[QueryDraft] = Field(default_factory=list)
    original_input: str = Field(default="", max_length=1000)
    fashion_intent: FashionIntent | None = None


class SearchRequest(BaseModel):
    queries: list[QueryDraft]
    # Keep the combination pool bounded: five candidates per garment query are
    # enough for diversity while avoiding an expensive cartesian explosion.
    top_k: int = Field(default=7, ge=1, le=7)
    user_key: str = Field(default="demo-user", min_length=1, max_length=120)
    user_input: str = Field(default="", max_length=1200)
    audience: Audience | None = None
    requirements: RequirementSummary | None = None
    styling_guide: StylingGuide | None = None
    shoe_specs: dict[str, ShoeSpec] = Field(default_factory=dict)
    shortlist_count: int = Field(default=30, ge=5, le=30)
    fashion_intent: FashionIntent | None = None
    final_count: int = Field(default=10, ge=1, le=10)
    use_aesthetic_review: bool = True
    include_debug: bool = False


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
    # A request-scoped image supplied by the user, rather than a row in `clothes`.
    is_reference: bool = False
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
    local_fallback_fields: list[str] = Field(default_factory=list)
    silhouette_proportion: int | None = Field(default=None, ge=0, le=100)
    pairing_coherence: int | None = Field(default=None, ge=0, le=100)
    color_material_harmony: int | None = Field(default=None, ge=0, le=100)
    constraint_compliance: int | None = Field(default=None, ge=0, le=100)
    style_drift_detected: bool = False
    style_drift_evidence: list[str] = Field(default_factory=list)
    style_identity_match: int | None = Field(default=None, ge=0, le=100)
    inner_layer_suggestion: str = Field(default="", max_length=600)
    occasion_fit: int = Field(ge=0, le=100)
    color_harmony: int = Field(ge=0, le=100)
    silhouette_balance: int = Field(ge=0, le=100)
    material_coherence: int = Field(ge=0, le=100)
    overall_aesthetic: int = Field(ge=0, le=100)
    fatal_issues: list[str] = Field(default_factory=list)
    reason: str
    knowledge_observation_ids: list[str] = Field(default_factory=list)


class ShoeSuggestion(BaseModel):
    query: str
    item_id: int
    retrieval_score: float
    added_after_review: bool = True


class ShoeRetrievalDebug(BaseModel):
    """One strict-shoe retrieval trace for a final outfit."""

    outfit_id: str
    original_query: str
    query: str
    requested_type: str = ""
    requested_color: str = ""
    candidates: list[ClothResult] = Field(default_factory=list)
    selected_item_id: int | None = None


class OutfitRecommendation(BaseModel):
    id: str
    kind: Literal["separates", "one_piece"]
    direction_id: str | None = None
    items: list[ClothResult]
    score: float
    reasons: list[str]
    references: list[ReferenceLink] = Field(default_factory=list)
    score_breakdown: OutfitScoreBreakdown | None = None
    aesthetic_review: AestheticReview | None = None
    shoe_suggestion: ShoeSuggestion | None = None


class RecommendationDebug(BaseModel):
    search_results: list[QuerySearchResult] = Field(default_factory=list)
    ranked_candidate_count: int = 0
    ranked_preview: list[OutfitRecommendation] = Field(default_factory=list)
    shortlist_before_review: list[OutfitRecommendation] = Field(default_factory=list)
    knowledge_observations: list[OutfitObservation] = Field(default_factory=list)
    aesthetic_review_attempted: bool = False
    aesthetic_review_error: str = ""
    aesthetic_review_diagnostics: dict = Field(default_factory=dict)
    stage_timings_ms: dict[str, float] = Field(default_factory=dict)
    compatibility_note: str = ""
    shoe_retrievals: list[ShoeRetrievalDebug] = Field(default_factory=list)


class RecommendationResponse(BaseModel):
    recommendations: list[OutfitRecommendation]
    discarded_recommendations: list[OutfitRecommendation] = Field(default_factory=list)
    aesthetic_reviewed: bool = False
    review_note: str = ""
    knowledge_observation_count: int = 0
    knowledge_sources: list[str] = Field(default_factory=list)
    knowledge_note: str = ""
    debug: RecommendationDebug | None = None


# ---------------------------------------------------------------------------
# User preferences
#
# Hard rules live on the ``user_hard_rules`` row and act as gates - they are
# translated into SQL filters on ``clothes``. Soft preferences are context-scoped
# sentences authored by the user or confirmed from liked outfits. They guide LLM
# stages but never alter rank scores directly.
# ---------------------------------------------------------------------------

PreferenceSource = Literal["explicit", "implicit"]
PreferenceType = Literal["prefer", "avoid"]
ProfileGender = Literal["female", "male", "non_binary", "prefer_not_to_say"]


class HardRules(BaseModel):
    gender: ProfileGender | None = None
    age: int | None = Field(default=None, ge=1, le=120)
    height_cm: float | None = Field(default=None, ge=50, le=250)
    weight_kg: float | None = Field(default=None, ge=10, le=400)
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
    occasions: list[str] = Field(default_factory=list)
    seasons: list[str] = Field(default_factory=list)
    times_of_day: list[str] = Field(default_factory=list)
    climates: list[str] = Field(default_factory=list)
    formalities: list[str] = Field(default_factory=list)
    activities: list[str] = Field(default_factory=list)
    styles: list[str] = Field(default_factory=list)


class StylePreferenceCreate(StylePreferenceBase):
    preference_type: PreferenceType = "prefer"
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
    requirements: RequirementSummary | None = None


class StylePreferenceAddRequest(BaseModel):
    """A deliberate like/dislike reaction to one or more catalog items.

    ``user_request`` is the in-flight search text when the reaction comes from a
    recommendation card; it is absent when reacting from a plain catalog listing.
    """

    user_key: str = Field(default="demo-user", min_length=1, max_length=120)
    user_request: str | None = Field(default=None, max_length=1200)
    outfit_item_ids: list[int] = Field(min_length=1)
    preference_type: PreferenceType
    requirements: RequirementSummary | None = None


class StylePreferenceItemProposalRequest(BaseModel):
    item_id: int = Field(gt=0)


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


class FavoriteItem(BaseModel):
    item: CatalogItem
    favorited_at: datetime


class FavoriteOutfit(BaseModel):
    id: int
    favorited_at: datetime
    items: list[CatalogItem] = Field(min_length=2)


class FavoriteCollection(BaseModel):
    user_key: str
    items: list[FavoriteItem] = Field(default_factory=list)
    outfits: list[FavoriteOutfit] = Field(default_factory=list)


class FavoriteItemsUpdate(BaseModel):
    item_ids: list[int] = Field(min_length=1, max_length=100)
    favorited: bool


class FavoriteOutfitUpdate(BaseModel):
    item_ids: list[int] = Field(min_length=2, max_length=100)
    favorited: bool

    @model_validator(mode="after")
    def _require_two_distinct_items(self) -> "FavoriteOutfitUpdate":
        if len(set(self.item_ids)) < 2:
            raise ValueError("An outfit requires at least two distinct item IDs")
        return self


class FavoriteItemsMutationResponse(BaseModel):
    user_key: str
    added: int = 0
    removed: int = 0
    favorite_item_ids: list[int] = Field(default_factory=list)


class CatalogResponse(BaseModel):
    items: list[CatalogItem]
    total: int


class CatalogSemanticSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=240)
    zone: GarmentZone | None = None
    limit: int = Field(default=60, ge=1, le=100)
    user_key: str = Field(default="demo-user", min_length=1, max_length=120)
    audience: Audience | None = None
    requirements: RequirementSummary | None = None


class CatalogSemanticSearchResponse(BaseModel):
    query: str
    items: list[ClothResult]
    total: int
    model: str
