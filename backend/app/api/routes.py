from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def api_health_check() -> dict[str, str]:
    return {"status": "ok"}
