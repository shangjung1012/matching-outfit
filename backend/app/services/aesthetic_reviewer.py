import base64
import io
import json
from pathlib import Path

from PIL import Image, ImageOps
from pydantic import BaseModel, Field

from app.schemas import AestheticReview, OutfitRecommendation
from app.services.outfit_ranker import select_diverse
from app.services.structured_llm import StructuredLLM

AESTHETIC_REVIEW_PROMPT = """
You are the final visual outfit critic for a practical recommendation system.
Judge the actual catalog garment images as one outfit, in light of the original user
request. Assess occasion fit, color harmony, silhouette balance, material coherence,
and overall contemporary aesthetic quality. Treat strict dress codes as gates, but do
not over-constrain ordinary leisure contexts. Product images are isolated cutouts, so
do not invent body fit, exact fabric composition, or styling details that are not
visible. Use the full 0-100 scale. Add fatal_issues only for concrete problems severe
enough that the outfit should not be recommended. Return one review for every supplied
candidate_id and concise Traditional Chinese reasons.
""".strip()


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
    def __init__(self, llm: StructuredLLM, model: str):
        self.llm = llm
        self.model = model

    def review(
        self,
        user_input: str,
        recommendations: list[OutfitRecommendation],
    ) -> dict[str, AestheticReview]:
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
                    {"user_request": user_input, "candidates": metadata},
                    ensure_ascii=False,
                ),
            },
        )
        result = self.llm.parse(
            model=self.model,
            instructions=AESTHETIC_REVIEW_PROMPT,
            content=content,
            schema=AestheticReviewBatch,
        )
        if not result.reviews:
            raise RuntimeError("The aesthetic reviewer returned no candidate reviews")
        return {
            review.candidate_id: AestheticReview.model_validate(
                review.model_dump(exclude={"candidate_id"})
            )
            for review in result.reviews
        }


def apply_aesthetic_reviews(
    recommendations: list[OutfitRecommendation],
    reviews: dict[str, AestheticReview],
    *,
    final_count: int,
) -> list[OutfitRecommendation]:
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
        rescored.append(
            recommendation.model_copy(
                update={
                    "score": round(max(0.0, min(1.0, final_score)), 4),
                    "score_breakdown": breakdown,
                    "aesthetic_review": review,
                    "reasons": [*recommendation.reasons, review.reason],
                }
            )
        )
    rescored.sort(key=lambda result: result.score, reverse=True)
    return select_diverse(rescored, final_count)
