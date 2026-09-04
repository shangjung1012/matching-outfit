from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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
