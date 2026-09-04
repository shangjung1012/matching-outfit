from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    times_of_day: list[str] = Field(default_factory=list)
    formalities: list[str] = Field(default_factory=list)
    activities: list[str] = Field(default_factory=list)
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


class FashionKnowledgeStatus(StrictModel):
    article_count: int
    observation_count: int
    embedded_observation_count: int = 0
    audience_counts: dict[str, int] = Field(default_factory=dict)
    data_dir: str


class FashionObservationAdminView(StrictModel):
    id: int
    observation_id: str
    summary: str
    evidence: str
    audiences: list[str] = Field(default_factory=list)
    occasions: list[str] = Field(default_factory=list)
    climates: list[str] = Field(default_factory=list)
    seasons: list[str] = Field(default_factory=list)
    times_of_day: list[str] = Field(default_factory=list)
    formalities: list[str] = Field(default_factory=list)
    activities: list[str] = Field(default_factory=list)
    styles: list[str] = Field(default_factory=list)
    garments: list[str] = Field(default_factory=list)
    colors: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    silhouettes: list[str] = Field(default_factory=list)
    styling_actions: list[str] = Field(default_factory=list)
    avoid_when: list[str] = Field(default_factory=list)
    signal_type: str
    confidence: float
    is_active: bool
    has_embedding: bool


class FashionArticleAdminView(StrictModel):
    id: int
    source_url: str
    source_name: str
    title: str
    author: str | None = None
    published_at: datetime | None = None
    collected_at: datetime
    language: str | None = None
    article_summary: str
    extraction_notes: list[str] = Field(default_factory=list)
    extraction_model: str
    observation_count: int
    active_observation_count: int
    observations: list[FashionObservationAdminView] = Field(default_factory=list)


class FashionArticleList(StrictModel):
    items: list[FashionArticleAdminView]
    total: int


class FashionArticleCollectRequest(StrictModel):
    urls: list[str] = Field(default_factory=list)
    raw_text: str = ""
    force_refresh: bool = False
    @model_validator(mode="after")
    def require_input(self):
        if not self.urls and not self.raw_text.strip():
            raise ValueError("請提供文章網址或貼上文字")
        return self
    download_images: bool = False
    max_images: int = Field(default=4, ge=0, le=4)


class FashionArticleCollectResult(StrictModel):
    url: str
    status: Literal["created", "updated", "failed", "skipped", "unsupported"]
    category: str = ""
    article_id: int | None = None
    title: str | None = None
    observation_count: int = 0
    message: str = ""


class FashionArticleCollectResponse(StrictModel):
    results: list[FashionArticleCollectResult]
    succeeded: int
    failed: int
    skipped: int = 0
    unsupported: int = 0


class FashionObservationPatch(StrictModel):
    is_active: bool


class FashionKnowledgeSourceView(StrictModel):
    key: str
    name: str
    index_url: str
    audience: Literal["men", "women"]


class FashionArticleAutoUpdateRequest(StrictModel):
    source_keys: list[str] = Field(default_factory=list)
    per_source_limit: int = Field(default=2, ge=1, le=20)
    page_limit: int = Field(default=0, ge=0, le=200)
    max_articles: int = Field(default=8, ge=1, le=12)


class FashionArticleAutoUpdateResponse(StrictModel):
    discovered: int
    skipped_existing: int
    candidates: list[str] = Field(default_factory=list)
    discovery_errors: dict[str, str] = Field(default_factory=dict)
    results: list[FashionArticleCollectResult] = Field(default_factory=list)
    succeeded: int
    failed: int


class FashionKnowledgeSnapshotObservation(StrictModel):
    observation_id: str
    summary: str
    evidence: str
    audiences: list[str] = Field(default_factory=list)
    occasions: list[str] = Field(default_factory=list)
    climates: list[str] = Field(default_factory=list)
    seasons: list[str] = Field(default_factory=list)
    times_of_day: list[str] = Field(default_factory=list)
    formalities: list[str] = Field(default_factory=list)
    activities: list[str] = Field(default_factory=list)
    styles: list[str] = Field(default_factory=list)
    garments: list[str] = Field(default_factory=list)
    colors: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    silhouettes: list[str] = Field(default_factory=list)
    styling_actions: list[str] = Field(default_factory=list)
    avoid_when: list[str] = Field(default_factory=list)
    signal_type: Literal["timeless", "current_trend", "editorial_example"]
    confidence: float = Field(ge=0, le=1)
    embedding_base64: str | None = None
    embedding_model: str | None = None
    is_active: bool = True
    reviewed_at: datetime | None = None


class FashionKnowledgeSnapshotArticle(StrictModel):
    source_url: str
    source_name: str
    title: str
    author: str | None = None
    published_at: datetime | None = None
    collected_at: datetime
    language: str | None = None
    article_summary: str
    extraction_notes: list[str] = Field(default_factory=list)
    extraction_model: str
    extracted_at: datetime
    observations: list[FashionKnowledgeSnapshotObservation] = Field(default_factory=list)


class FashionKnowledgeSnapshot(StrictModel):
    schema_version: Literal[1] = 1
    generated_at: datetime
    embedding_dimensions: int = Field(gt=0)
    content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    articles: list[FashionKnowledgeSnapshotArticle] = Field(default_factory=list)
