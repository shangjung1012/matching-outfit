"""Maintains one free-form, LLM-integrated personal summary per user."""

import json
import logging
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.user_preference import UserHardRule, UserStylePreference
from app.models.user_summary import UserSummary
from app.preferences.context import (
    build_planner_preference_context,
    outfit_context_embedding_text,
)
from app.schemas.workflow import OutfitRecommendation, RequirementSummary
from app.services.integration_tools.llm import LLM

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"
USER_SUMMARY_PROMPT = (PROMPTS_DIR / "UserSummaryWriter.txt").read_text(encoding="utf-8").strip()


class UserSummaryResult(BaseModel):
    summary: str = Field(min_length=1, max_length=600)


def user_summary_for(db: Session, user_key: str) -> UserSummary | None:
    return db.scalar(select(UserSummary).where(UserSummary.user_key == user_key))


def _final_outfits_payload(final_outfits: list[OutfitRecommendation]) -> list[dict]:
    return [
        {
            "items": [
                {
                    "name": item.product_display_name,
                    "colour": item.base_colour,
                    "article_type": item.article_type,
                    "zone": item.garment_zone,
                }
                for item in outfit.items
            ]
        }
        for outfit in final_outfits
    ]


def regenerate_user_summary(
    user_key: str,
    user_input: str,
    requirements: RequirementSummary | None,
    final_outfits: list[OutfitRecommendation],
) -> None:
    """Background task: integrate the just-completed session into a freshly
    rewritten summary. Must never raise - failures are logged and swallowed,
    matching the aesthetic-review graceful-degradation pattern. Opens its own
    Session because the request-scoped one may already be closed by the time
    a BackgroundTasks callback runs (it executes after the response is sent).
    """
    if not settings.user_summary_enabled or not settings.openai_api_key:
        return
    if not final_outfits:
        return
    db = SessionLocal()
    try:
        hard = db.scalar(select(UserHardRule).where(UserHardRule.user_key == user_key))
        style_preferences = list(
            db.scalars(
                select(UserStylePreference).where(
                    UserStylePreference.user_key == user_key,
                    UserStylePreference.is_active.is_(True),
                )
            )
        )
        existing = user_summary_for(db, user_key)
        payload = {
            "previous_summary": existing.summary_text if existing and existing.summary_text else "",
            "structured_preferences": build_planner_preference_context(hard, style_preferences),
            "latest_session": {
                "user_request": user_input,
                "session_context": outfit_context_embedding_text(requirements),
                "recommended_outfits": _final_outfits_payload(final_outfits),
            },
        }
        result = LLM().parse(
            stage="user_summary",
            instructions=USER_SUMMARY_PROMPT,
            content=[{"type": "input_text", "text": json.dumps(payload, ensure_ascii=False)}],
            schema=UserSummaryResult,
        )
        if existing is None:
            existing = UserSummary(user_key=user_key)
            db.add(existing)
        existing.summary_text = result.summary.strip()
        db.commit()
    except Exception:
        logger.exception("user_summary_update_failed user_key=%s", user_key)
        db.rollback()
    finally:
        db.close()
