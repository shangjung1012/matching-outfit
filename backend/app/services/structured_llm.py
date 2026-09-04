import base64
import io
from pathlib import Path
from typing import TypeVar

from openai import OpenAI, OpenAIError
from PIL import Image
from pydantic import BaseModel


SchemaT = TypeVar("SchemaT", bound=BaseModel)


class StructuredLLM:
    def __init__(self, api_key: str | None):
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for article extraction and styling")
        self.client = OpenAI(api_key=api_key)

    def parse(
        self,
        *,
        model: str,
        instructions: str,
        content: list[dict],
        schema: type[SchemaT],
    ) -> SchemaT:
        try:
            response = self.client.responses.parse(
                model=model,
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
