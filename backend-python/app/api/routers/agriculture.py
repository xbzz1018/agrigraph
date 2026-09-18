"""农业实体、症状反查、图谱探索、图片和混合检索接口。"""

import mimetypes
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, Response

from app.api.dependencies import current_principal, get_container
from app.api.responses import envelope
from app.core.container import AppContainer
from app.core.security import Principal

router = APIRouter(prefix="/api/v1", tags=["agriculture"])


@router.get("/agriculture/growth-stages")
def growth_stages(
    crop: str = "水稻",
    _principal: Principal = Depends(current_principal),
    container: AppContainer = Depends(get_container),
):
    return envelope(container.agriculture.growth_stages(crop))


@router.get("/agriculture/entities")
def entities(
    crop: str = "番茄",
    category: str = "",
    part: str = "",
    keyword: str = "",
    imageStatus: str = "",
    page: int = 1,
    pageSize: int = 20,
    _principal: Principal = Depends(current_principal),
    container: AppContainer = Depends(get_container),
):
    return envelope(
        container.agriculture.list_entities(
            crop, category, part, keyword, imageStatus, max(1, page), min(max(1, pageSize), 100)
        )
    )


@router.get("/agriculture/entities/symptom-candidates")
def symptom_candidates(
    crop: str = "番茄",
    symptoms: str = "",
    parts: str = "",
    limit: int = 12,
    _principal: Principal = Depends(current_principal),
    container: AppContainer = Depends(get_container),
):
    return envelope(container.agriculture.symptom_candidates(crop, symptoms, parts, min(max(1, limit), 50)))


@router.post("/agriculture/entities/compare")
def compare_entities(
    body: dict[str, Any],
    _principal: Principal = Depends(current_principal),
    container: AppContainer = Depends(get_container),
):
    return envelope(container.agriculture.compare([str(item) for item in body.get("entityIds", [])]))


@router.get("/agriculture/entities/{entity_id}")
def entity_detail(
    entity_id: str, _principal: Principal = Depends(current_principal), container: AppContainer = Depends(get_container)
):
    return envelope(container.agriculture.entity(entity_id))


@router.get("/agriculture/entities/{entity_id}/images")
def entity_images(
    entity_id: str, _principal: Principal = Depends(current_principal), container: AppContainer = Depends(get_container)
):
    return envelope(container.agriculture.entity(entity_id)["images"])


@router.get("/agriculture/entities/{entity_id}/similar")
def similar_entities(
    entity_id: str,
    limit: int = 6,
    _principal: Principal = Depends(current_principal),
    container: AppContainer = Depends(get_container),
):
    return envelope(container.agriculture.similar(entity_id, min(max(1, limit), 20)))


@router.get("/agriculture/entities/{entity_id}/relations")
def entity_relations(
    entity_id: str, _principal: Principal = Depends(current_principal), container: AppContainer = Depends(get_container)
):
    return envelope(container.agriculture.relations(entity_id))


@router.get("/graph/suggestions")
def graph_suggestions(
    query: str,
    crop: str = "",
    limit: int = 12,
    _principal: Principal = Depends(current_principal),
    container: AppContainer = Depends(get_container),
):
    return envelope(container.agriculture.suggestions(query, crop, min(max(1, limit), 50)))


@router.get("/graph/overview")
def graph_overview(
    crop: str = "番茄",
    _principal: Principal = Depends(current_principal),
    container: AppContainer = Depends(get_container),
):
    return envelope(container.agriculture.overview(crop))


@router.get("/graph/explore")
def graph_explore(
    rootId: str,
    relationTypes: str = "",
    relationType: str = "",
    _principal: Principal = Depends(current_principal),
    container: AppContainer = Depends(get_container),
):
    return envelope(container.agriculture.graph(rootId, relationTypes or relationType))


@router.get("/graph/path")
def graph_path(
    sourceId: str,
    targetId: str,
    maxDepth: int = 4,
    _principal: Principal = Depends(current_principal),
    container: AppContainer = Depends(get_container),
):
    return envelope(container.agriculture.path(sourceId, targetId, maxDepth))


@router.get("/graph/related-entities")
def graph_related(
    nodeId: str,
    crop: str = "",
    limit: int = 12,
    _principal: Principal = Depends(current_principal),
    container: AppContainer = Depends(get_container),
):
    return envelope(container.agriculture.related_entities(nodeId, crop, min(max(1, limit), 50)))


@router.get("/graph/search")
def graph_search(
    query: str,
    limit: int = 30,
    _principal: Principal = Depends(current_principal),
    container: AppContainer = Depends(get_container),
):
    return envelope(container.agriculture.suggestions(query, "", min(max(1, limit), 100)))


@router.get("/graph/entities/{entity_id}")
def graph_entity(
    entity_id: str, _principal: Principal = Depends(current_principal), container: AppContainer = Depends(get_container)
):
    return envelope(container.agriculture.entity(entity_id))


@router.get("/graph/entities/{entity_id}/neighborhood")
def graph_neighborhood(
    entity_id: str,
    depth: int = 1,
    _principal: Principal = Depends(current_principal),
    container: AppContainer = Depends(get_container),
):
    return envelope(container.agriculture.graph(entity_id))


@router.get("/search")
def agriculture_search(
    query: str,
    topK: int = 10,
    _principal: Principal = Depends(current_principal),
    container: AppContainer = Depends(get_container),
):
    return envelope(container.agriculture.search(query, min(max(1, topK), 100)))


@router.get("/media/images/{image_id}")
def media_image(image_id: str, container: AppContainer = Depends(get_container)):
    object_key = container.agriculture.image_object_key(image_id)
    if not object_key:
        return Response(status_code=404)
    settings = container.settings
    root = settings.data_root.resolve()
    local = (root / object_key.replace("\\", "/")).resolve()
    if local.is_relative_to(root) and local.is_file():
        media_type = mimetypes.guess_type(local.name)[0] or "application/octet-stream"
        return FileResponse(local, media_type=media_type, headers={"Cache-Control": "public, max-age=604800"})
    return Response(status_code=404)
