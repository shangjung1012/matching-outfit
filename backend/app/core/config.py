from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://matching_user:matching_password@localhost:5432/matching_outfit"
    backend_cors_origins: str = "http://localhost:5173"
    image_dir: str = "/data/images"
    fashion_clip_model: str = "patrickjohncyh/fashion-clip"
    embedding_batch_size: int = 16

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]


settings = Settings()
