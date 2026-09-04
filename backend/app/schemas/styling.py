from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.workflow import OutfitRecommendation


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ArticleImage(StrictModel):
    url: str
    alt: str = ""
    caption: str = ""
    local_path: str | None = None


class ArticleBlock(StrictModel):
    heading: str = ""
    text: str
    image_indexes: list[int] = Field(default_factory=list)


class CollectedArticle(StrictModel):
    source_url: str
    source_name: str
    title: str
    author: str | None = None
    published_at: str | None = None
    collected_at: datetime
    language: str | None = None
    text: str
    blocks: list[ArticleBlock] = Field(default_factory=list)
    images: list[ArticleImage] = Field(default_factory=list)


class ArticleSource(StrictModel):
    source_url: str
    source_name: str
    title: str
    author: str | None = None
    published_at: str | None = None
    collected_at: datetime
    language: str | None = None


class OutfitObservation(StrictModel):
    observation_id: str = ""
    source_url: str = ""
    source_name: str = ""
    source_title: str = ""
    published_at: str | None = None
    summary: str = Field(description="A short, reusable outfit observation")
    evidence: str = Field(description="Short supporting phrase paraphrased from the article or image")
    audiences: list[Literal["men", "women", "unisex"]] = Field(default_factory=list)
    occasions: list[str] = Field(default_factory=list)
    climates: list[str] = Field(default_factory=list)
    seasons: list[str] = Field(default_factory=list)
    styles: list[str] = Field(default_factory=list)
    garments: list[str] = Field(default_factory=list)
    colors: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    silhouettes: list[str] = Field(default_factory=list)
    styling_actions: list[str] = Field(default_factory=list)
    avoid_when: list[str] = Field(default_factory=list)
    signal_type: Literal["timeless", "current_trend", "editorial_example"]
    confidence: float = Field(ge=0, le=1)


class ArticleExtraction(StrictModel):
    article_summary: str
    observations: list[OutfitObservation]
    extraction_notes: list[str] = Field(default_factory=list)


class KnowledgeRecord(StrictModel):
    article: ArticleSource
    extraction: ArticleExtraction
    extracted_at: datetime
    extraction_model: str


class StylingDemoRequest(StrictModel):
    user_input: str = Field(min_length=2, max_length=1200)
    audience: Literal["men", "women", "unisex"] | None = None
    top_k_observations: int = Field(default=8, ge=1, le=20)
    revise_once: bool = True


class RequestInterpretation(StrictModel):
    occasion: str
    context_restrictiveness: Literal["low", "medium", "high"]
    hard_constraints: list[str] = Field(default_factory=list)
    soft_preferences: list[str] = Field(default_factory=list)
    aesthetic_direction: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class GarmentSearchSpec(StrictModel):
    garment_zone: Literal["upper_body", "lower_body", "one_piece", "accessory"]
    query: str = Field(
        description="Concise English visual description for FashionCLIP text-to-image search"
    )
    rationale: str


class OutfitFormula(StrictModel):
    name: str
    items: list[str]
    palette: list[str]
    silhouette: str
    materials: list[str] = Field(default_factory=list)
    styling_notes: list[str] = Field(default_factory=list)
    why_it_works: str
    context_fit: str
    source_observation_ids: list[str] = Field(default_factory=list)
    search_specs: list[GarmentSearchSpec] = Field(
        description="Zone-specific FashionCLIP searches needed to instantiate the outfit"
    )


class StylingDraft(StrictModel):
    interpretation: RequestInterpretation
    outfits: list[OutfitFormula] = Field(min_length=3, max_length=3)
    selection_guidance: list[str] = Field(default_factory=list)


class StylingCritique(StrictModel):
    verdict: Literal["pass", "revise"]
    strengths: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    revision_instructions: list[str] = Field(default_factory=list)


class StylingDemoResponse(StrictModel):
    request: str
    retrieved_observations: list[OutfitObservation]
    initial_draft: StylingDraft
    critique: StylingCritique
    final_draft: StylingDraft
    revised: bool


class StylingCatalogRequest(StylingDemoRequest):
    user_key: str = Field(default="demo-user", min_length=1, max_length=120)
    candidates_per_zone: int = Field(default=8, ge=2, le=30)
    outfits_per_formula: int = Field(default=3, ge=1, le=8)


class FormulaCatalogMatch(StrictModel):
    formula: OutfitFormula
    recommendations: list[OutfitRecommendation]


class StylingCatalogResponse(StrictModel):
    styling: StylingDemoResponse
    matches: list[FormulaCatalogMatch]
    embedding_model: str


class FashionKnowledgeStatus(StrictModel):
    article_count: int
    observation_count: int
    embedded_observation_count: int = 0
    audience_counts: dict[str, int] = Field(default_factory=dict)
    data_dir: str
