from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://matching_user:matching_password@localhost:5432/matching_outfit"
    backend_cors_origins: str = "http://localhost:5173"
    image_dir: str = "/data/images"
    wardrobe_dir: str = "/data/wardrobe"
    fashion_clip_model: str = "patrickjohncyh/fashion-clip"
    embedding_batch_size: int = 16

    tryon_api_url: str = ""
    tryon_api_key: str = ""
    tryon_request_timeout_seconds: float = 300.0
    human3d_request_timeout_seconds: float = 900.0
    image_max_upload_bytes: int = 10 * 1024 * 1024
    image_max_pixels: int = 20_000_000
    catalog_currency: str = "INR"
    article_data_dir: str = "/data/articles"
    article_allowed_domains: str = (
        "vogue.com,gq.com,instyle.com,theguardian.com,elle.com,www.elle.com,gq.com.tw,www.gq.com.tw,"
        "marieclairekorea.com,www.marieclairekorea.com,gqkorea.co.kr,www.gqkorea.co.kr"
    )
    article_user_agent: str = "MatchingOutfitResearchBot/0.1"
    openai_api_key: str | None = None
    article_extraction_model: str = "gpt-4.1-mini"
    query_planner_model: str = "gpt-4.1-mini"
    fashion_intent_interpreter_enabled: bool = True
    aesthetic_review_model: str = "gpt-4.1-mini"
    aesthetic_review_enabled: bool = True
    # Keep the parsed total budget visible in the request for now, but do not
    # let it eliminate final recommendations until catalog currency is unified.
    outfit_budget_filter_enabled: bool = False
    knowledge_embedding_model: str = "text-embedding-3-small"
    knowledge_embedding_dimensions: int = 512


    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]

    @property
    def allowed_article_domains(self) -> set[str]:
        return {
            domain.strip().lower()
            for domain in self.article_allowed_domains.split(",")
            if domain.strip()
        }


settings = Settings()
