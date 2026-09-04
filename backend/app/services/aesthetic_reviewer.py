import base64
import io
import json
from pathlib import Path

from PIL import Image, ImageOps
from pydantic import BaseModel, Field

from app.schemas import AestheticReview, OutfitRecommendation, ReferenceLink, StylingGuide
from app.schemas.fashion_knowledge import OutfitObservation
from app.services.outfit_ranker import select_diverse
from app.services.integration_tools.llm import LLM

PROMPTS_DIR = Path(__file__).parent / "prompts"
AESTHETIC_REVIEW_PROMPT = (PROMPTS_DIR / "AestheticReviewer.txt").read_text(
    encoding="utf-8"
).strip()


class CandidateAestheticReview(AestheticReview):
    candidate_id: str


class AestheticReviewBatch(BaseModel):
    reviews: list[CandidateAestheticReview] = Field(default_factory=list)


def outfit_contact_sheet_data_url(
    recommendation: OutfitRecommendation,
    *,
    item_width: int = 320,
    item_height: int = 420,
) -> str | None:
    panels: list[Image.Image] = []
    for item in recommendation.items:
        if not item.image_path:
            continue
        path = Path(item.image_path)
        if not path.exists():
            continue
        try:
            with Image.open(path) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
                image.thumbnail((item_width - 24, item_height - 24))
                panel = Image.new("RGB", (item_width, item_height), "white")
                panel.paste(
                    image,
                    ((item_width - image.width) // 2, (item_height - image.height) // 2),
                )
                panels.append(panel)
        except OSError:
            continue
    if not panels:
        return None
    sheet = Image.new("RGB", (item_width * len(panels), item_height), "white")
    for index, panel in enumerate(panels):
        sheet.paste(panel, (index * item_width, 0))
    buffer = io.BytesIO()
    sheet.save(buffer, format="JPEG", quality=80, optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


class AestheticReviewer:
    def __init__(self, llm: LLM):
        self.llm = llm

    def review(
        self,
        user_input: str,
        recommendations: list[OutfitRecommendation],
        *,
        observations: list[OutfitObservation] | None = None,
        user_preferences: dict | None = None,
        styling_guide: StylingGuide | None = None,
    ) -> dict[str, AestheticReview]:
        observations = observations or []
        metadata = []
        content: list[dict] = []
        for recommendation in recommendations:
            image_url = outfit_contact_sheet_data_url(recommendation)
            if image_url is None:
                continue
            metadata.append(
                {
                    "candidate_id": recommendation.id,
                    "match_score": recommendation.score,
                    "items": [
                        {
                            "zone": item.garment_zone,
                            "name": item.product_display_name,
                            "color": item.base_colour,
                            "article_type": item.article_type,
                            "usage": item.usage,
                        }
                        for item in recommendation.items
                    ],
                }
            )
            content.extend(
                [
                    {
                        "type": "input_text",
                        "text": f"Candidate {recommendation.id} composite image:",
                    },
                    {"type": "input_image", "image_url": image_url, "detail": "low"},
                ]
            )
        if not metadata:
            raise RuntimeError("No readable candidate images were available for aesthetic review")
        content.insert(
            0,
            {
                "type": "input_text",
                "text": json.dumps(
                    {
                        "user_request": user_input,
                        "styling_guide": (
                            styling_guide.model_dump(mode="json") if styling_guide else None
                        ),
                        "user_preferences": user_preferences or {},
                        "fashion_observations": [
                            {
                                "observation_id": observation.observation_id,
                                "summary": observation.summary,
                                "evidence": observation.evidence,
                                "occasions": observation.occasions,
                                "climates": observation.climates,
                                "seasons": observation.seasons,
                                "times_of_day": observation.times_of_day,
                                "formalities": observation.formalities,
                                "activities": observation.activities,
                                "styles": observation.styles,
                                "garments": observation.garments,
                                "colors": observation.colors,
                                "materials": observation.materials,
                                "silhouettes": observation.silhouettes,
                                "styling_actions": observation.styling_actions,
                                "avoid_when": observation.avoid_when,
                                "signal_type": observation.signal_type,
                                "confidence": observation.confidence,
                            }
                            for observation in observations
                        ],
                        "candidates": metadata,
                    },
                    ensure_ascii=False,
                ),
            },
        )
        result = self.llm.parse(
            stage="aesthetic_review",
            instructions=AESTHETIC_REVIEW_PROMPT,
            content=content,
            schema=AestheticReviewBatch,
        )
        if not result.reviews:
            raise RuntimeError("The aesthetic reviewer returned no candidate reviews")
        valid_observation_ids = {
            observation.observation_id for observation in observations
        }
        return {
            review.candidate_id: AestheticReview.model_validate(
                {
                    **review.model_dump(exclude={"candidate_id"}),
                    "knowledge_observation_ids": list(
                        dict.fromkeys(
                            identifier
                            for identifier in review.knowledge_observation_ids
                            if identifier in valid_observation_ids
                        )
                    ),
                }
            )
            for review in result.reviews
        }


def apply_aesthetic_reviews(
    recommendations: list[OutfitRecommendation],
    reviews: dict[str, AestheticReview],
    *,
    final_count: int,
    observations: list[OutfitObservation] | None = None,
) -> list[OutfitRecommendation]:
    observations_by_id = {
        observation.observation_id: observation for observation in observations or []
    }
    rescored: list[OutfitRecommendation] = []
    for recommendation in recommendations:
        review = reviews.get(recommendation.id)
        if review is None:
            rescored.append(recommendation)
            continue
        aesthetic_score = (
            0.25 * review.occasion_fit
            + 0.20 * review.color_harmony
            + 0.15 * review.silhouette_balance
            + 0.10 * review.material_coherence
            + 0.30 * review.overall_aesthetic
        ) / 100
        final_score = 0.6 * recommendation.score + 0.4 * aesthetic_score
        if review.fatal_issues:
            final_score -= 0.18
        breakdown = recommendation.score_breakdown
        if breakdown is not None:
            breakdown = breakdown.model_copy(update={"aesthetic": round(aesthetic_score, 4)})
        references = []
        seen_urls: set[str] = set()
        for identifier in review.knowledge_observation_ids:
            observation = observations_by_id.get(identifier)
            if observation is None or not observation.source_url:
                continue
            if observation.source_url in seen_urls:
                continue
            seen_urls.add(observation.source_url)
            references.append(
                ReferenceLink(
                    title=(
                        observation.source_title
                        or observation.source_name
                        or observation.source_url
                    ),
                    url=observation.source_url,
                )
            )
        rescored.append(
            recommendation.model_copy(
                update={
                    "score": round(max(0.0, min(1.0, final_score)), 4),
                    "score_breakdown": breakdown,
                    "aesthetic_review": review,
                    "reasons": [*recommendation.reasons, review.reason],
                    "references": references,
                }
            )
        )
    rescored.sort(key=lambda result: result.score, reverse=True)
    return select_diverse(rescored, final_count)
