from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.api.try_on import router as try_on_router
from app.api.fashion_knowledge_admin import router as fashion_knowledge_admin_router
from app.core.config import settings

app = FastAPI(title="Matching Outfit API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
app.include_router(try_on_router, prefix="/api")
app.include_router(fashion_knowledge_admin_router, prefix="/api")

image_dir = Path(settings.image_dir)
image_dir.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=image_dir), name="media")


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
