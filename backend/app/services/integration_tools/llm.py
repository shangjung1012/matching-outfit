"""OpenAI Responses API adapter for structured LLM workflow stages."""

import base64
import io
from pathlib import Path
from typing import Literal, TypeVar

from openai import OpenAI, OpenAIError
from PIL import Image
from pydantic import BaseModel

from app.core.config import settings

SchemaT = TypeVar("SchemaT", bound=BaseModel)
LLMStage = Literal[
    "article_extraction",
    "query_planning",
    "query_repair",
    "aesthetic_review",
]

_STAGE_MODEL_SETTING = {
    "article_extraction": "article_extraction_model",
    "query_planning": "query_planner_model",
    "query_repair": "query_planner_model",
    "aesthetic_review": "aesthetic_review_model",
}


class LLM:
    """Application LLM gateway with centrally configured models per workflow stage."""

    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for LLM-backed workflows")
        self.client = OpenAI(api_key=settings.openai_api_key)

    @staticmethod
    def model_for(stage: LLMStage) -> str:
        return getattr(settings, _STAGE_MODEL_SETTING[stage])

    def parse(
        self,
        *,
        stage: LLMStage,
        instructions: str,
        content: list[dict],
        schema: type[SchemaT],
    ) -> SchemaT:
        try:
            response = self.client.responses.parse(
                model=self.model_for(stage),
                instructions=instructions,
                input=[{"role": "user", "content": content}],
                text_format=schema,
            )
        except OpenAIError as error:
            raise RuntimeError(f"OpenAI request failed: {error}") from error
        if response.output_parsed is None:
            raise RuntimeError("The model did not return a valid structured response")
        return response.output_parsed


def local_image_data_url(path: str, max_edge: int = 1024) -> str:
    with Image.open(Path(path)) as image:
        image = image.convert("RGB")
        image.thumbnail((max_edge, max_edge))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=82, optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"
