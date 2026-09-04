"""Generate conservative shoe retrieval briefs for ranked clothing candidates."""
import json
from pydantic import BaseModel, Field
from app.schemas import OutfitRecommendation, ShoeSpec
from app.services.integration_tools.llm import LLM

class PlannedShoe(BaseModel):
    candidate_id: str
    shoe_spec: ShoeSpec

class ShoePlanBatch(BaseModel):
    shoes: list[PlannedShoe] = Field(default_factory=list)

class ShoePlanner:
    def __init__(self, llm: LLM): self.llm = llm
    def plan(self, user_input: str, outfits: list[OutfitRecommendation]) -> dict[str, ShoeSpec]:
        if not outfits: return {}
        payload = {"user_request": user_input, "outfits": [{"candidate_id": outfit.id, "items": [
            {"zone": item.garment_zone, "name": item.product_display_name, "color": item.base_colour,
             "article_type": item.article_type, "usage": item.usage} for item in outfit.items]} for outfit in outfits]}
        result = self.llm.parse(stage="query_planning", instructions=(
            "For each clothing outfit return one conservative English shoe retrieval brief. "
            "Do not score or alter outfits. Prefer black, white, off-white, grey, beige, dark brown, or navy; "
            "coordinate with lower garment. A beige label can look yellow/orange/camel, so do not mistake it for neutral beige."),
            content=[{"type": "input_text", "text": json.dumps(payload, ensure_ascii=False)}], schema=ShoePlanBatch)
        valid = {outfit.id for outfit in outfits}
        return {item.candidate_id: item.shoe_spec for item in result.shoes if item.candidate_id in valid}
