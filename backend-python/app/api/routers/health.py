"""服务存活和核心依赖健康检查。"""

from fastapi import APIRouter, Depends

from app.agents.schemas import utc_now
from app.api.dependencies import get_container
from app.api.responses import envelope
from app.core.container import AppContainer

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health")
def health(container: AppContainer = Depends(get_container)):
    return envelope(
        {
            "status": "UP",
            "runtime": "python",
            "workflowMode": "DETERMINISTIC_MULTIMODAL_KNOWLEDGE",
            "retrievalMode": "bm25",
            "modelConfigured": container.model.enabled,
            "visionConfigured": container.vision.enabled,
            "supportedCrops": ["番茄", "水稻"],
            "timestamp": utc_now(),
        }
    )


@router.get("/health/dependencies")
def health_dependencies(container: AppContainer = Depends(get_container)):
    return envelope(container.dependency_health.check())
