from openai import OpenAI, OpenAIError


class TextEmbeddingService:
    def __init__(self, api_key: str | None, model: str, dimensions: int = 512):
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for fashion knowledge embeddings")
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.dimensions = dimensions

    def encode(self, texts: list[str], *, batch_size: int = 128) -> list[list[float]]:
        if not texts:
            return []
        if any(not text.strip() for text in texts):
            raise ValueError("Embedding inputs cannot be empty")
        vectors: list[list[float]] = []
        try:
            for start in range(0, len(texts), batch_size):
                response = self.client.embeddings.create(
                    model=self.model,
                    input=texts[start : start + batch_size],
                    dimensions=self.dimensions,
                    encoding_format="float",
                )
                vectors.extend(item.embedding for item in sorted(response.data, key=lambda item: item.index))
        except OpenAIError as error:
            raise RuntimeError(f"OpenAI embedding request failed: {error}") from error
        return vectors
