import base64
import io
import json
from pathlib import Path

from PIL import Image, ImageOps
from pydantic import BaseModel, Field

from app.schemas import AestheticReview, OutfitRecommendation, ReferenceLink, StylingGuide
from app.schemas.fashion_knowledge import OutfitObservation
from app.schemas.workflow import FashionIntent, RequirementSummary
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
    # Never review a two-piece outfit from only one readable garment image.
    if not panels or len(panels) != len(recommendation.items):
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
        self.last_debug: dict = {}

    def review(
        self,
        user_input: str,
        recommendations: list[OutfitRecommendation],
        *,
        observations: list[OutfitObservation] | None = None,
        user_preferences: dict | None = None,
        styling_guide: StylingGuide | None = None,
        requirements: RequirementSummary | None = None,
        fashion_intent: FashionIntent | None = None,
    ) -> dict[str, AestheticReview]:
        observations = observations or []
        self.last_debug = {
            "candidate_count": len(recommendations), "image_failures": [],
            "submitted_ids": [], "attempts": [], "missing_ids": [], "reviewed_count": 0,
        }
        metadata = []
        content: list[dict] = []
        for recommendation in recommendations:
            image_url = outfit_contact_sheet_data_url(recommendation)
            if image_url is None:
                failures = []
                for item in recommendation.items:
                    if not item.image_path:
                        failures.append({"item_id": item.id, "reason": "商品沒有本機圖片路徑"})
                        continue
                    try:
                        with Image.open(item.image_path) as image:
                            image.load()
                    except (OSError, ValueError) as error:
                        failures.append({"item_id": item.id, "reason": str(error)})
                self.last_debug["image_failures"].append({
                    "candidate_id": recommendation.id,
                    "items": failures,
                    "reason": "完整搭配圖片無法建立",
                })
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
                        "activity_context": fashion_intent.activity_context.model_dump(mode="json") if fashion_intent else None,
                        "forbidden_style_drift": fashion_intent.forbidden_style_drift if fashion_intent else [],
                        "body_context": fashion_intent.body_context.model_dump(mode="json") if fashion_intent else None,
                        "body_strategy": fashion_intent.body_strategy.model_dump(mode="json") if fashion_intent else None,
                        "requirement_summary": (
                            requirements.model_dump(mode="json") if requirements else None
                        ),
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
        valid_observation_ids = {
            observation.observation_id for observation in observations
        }
        submitted_ids = [candidate["candidate_id"] for candidate in metadata]
        self.last_debug["submitted_ids"] = submitted_ids
        header = json.loads(content[0]["text"])
        images_by_id = {
            identifier: content[1 + index * 2: 3 + index * 2]
            for index, identifier in enumerate(submitted_ids)
        }
        reviews: dict[str, AestheticReview] = {}

        def run_batch(ids: list[str], round_number: int) -> None:
            batch_header = {
                **header,
                "candidates": [candidate for candidate in metadata if candidate["candidate_id"] in ids],
                "required_candidate_ids": ids,
            }
            batch_content = [{"type": "input_text", "text": json.dumps(batch_header, ensure_ascii=False)}]
            for identifier in ids:
                batch_content.extend(images_by_id[identifier])
            attempt = {
                "round": round_number, "requested_ids": ids, "returned_ids": [],
                "invalid_ids": [], "duplicate_ids": [], "missing_ids": [], "error": "",
            }
            self.last_debug["attempts"].append(attempt)
            try:
                result = self.llm.parse(
                    stage="aesthetic_review",
                    instructions=AESTHETIC_REVIEW_PROMPT,
                    content=batch_content,
                    schema=AestheticReviewBatch,
                )
                seen: set[str] = set()
                for review in result.reviews:
                    identifier = review.candidate_id
                    attempt["returned_ids"].append(identifier)
                    if identifier not in ids:
                        attempt["invalid_ids"].append(identifier)
                        continue
                    if identifier in seen:
                        attempt["duplicate_ids"].append(identifier)
                        continue
                    seen.add(identifier)
                    appearance_led = (
                        fashion_intent is not None
                        and fashion_intent.activity_context.activity_mode == "appearance_led_performance"
                    )
                    if appearance_led and review.style_identity_match is None:
                        attempt.setdefault("incomplete_review_ids", []).append(identifier)
                        continue
                    accepted = AestheticReview.model_validate({
                        **review.model_dump(exclude={"candidate_id"}),
                        "knowledge_observation_ids": list(dict.fromkeys(
                            value for value in review.knowledge_observation_ids
                            if value in valid_observation_ids
                        )),
                    })
                    if appearance_led and accepted.style_identity_match < 50:
                        accepted = accepted.model_copy(update={
                            "overall_aesthetic": min(49, accepted.overall_aesthetic),
                            "fatal_issues": [*accepted.fatal_issues, "未符合要求的視覺風格；不以活動機能取代造型"],
                        })
                    reviews[identifier] = accepted
            except (RuntimeError, ValueError) as error:
                attempt["error"] = str(error)
            attempt["missing_ids"] = [identifier for identifier in ids if identifier not in reviews]

        # Preserve the initial single batch; retry only omissions, first in small
        # batches and then individually. Never regenerate already accepted scores.
        run_batch(submitted_ids, 0)
        for round_number, batch_size in ((1, 5), (2, 1)):
            missing = [identifier for identifier in submitted_ids if identifier not in reviews]
            for offset in range(0, len(missing), batch_size):
                run_batch(missing[offset:offset + batch_size], round_number)
        self.last_debug["missing_ids"] = [identifier for identifier in submitted_ids if identifier not in reviews]
        self.last_debug["reviewed_count"] = len(reviews)
        if not reviews:
            raise RuntimeError("美感審查及補審皆未取得有效評分；請查看審查除錯紀錄。")
        return reviews


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
        if "未符合要求的視覺風格；不以活動機能取代造型" in review.fatal_issues:
            final_score = min(final_score, 0.49)
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
    # Coverage/diversity quotas belong to the pre-review shortlist only.
    return rescored[:final_count]
