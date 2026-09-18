"""固定检索评测、批量对照和回答评测接口。"""

import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import APIRouter, Depends

from app.api.dependencies import current_principal, get_container
from app.api.responses import envelope
from app.api.schemas import ChatRequest
from app.core.container import AppContainer
from app.core.security import Principal

router = APIRouter(prefix="/api/v1/evaluation", tags=["evaluation"])


@router.get("/retrieve")
def evaluation_retrieve(
    query: str,
    crop: str = "AUTO",
    limit: int = 10,
    _principal: Principal = Depends(current_principal),
    container: AppContainer = Depends(get_container),
):
    return envelope(container.agriculture.evaluation_retrieve(query, crop, min(max(1, limit), 50)))


@router.post("/answer")
def evaluation_answer(
    body: dict[str, Any],
    principal: Principal = Depends(current_principal),
    container: AppContainer = Depends(get_container),
):
    question = str(body.get("question", "")).strip()
    if not question:
        raise ValueError("评测问题不能为空")
    request = ChatRequest(question=question, cropScope=str(body.get("crop", "AUTO")), knowledgeEnhanced=True)
    return envelope(container.agent_service.run(principal.username, str(uuid.uuid4()), request, "evaluation"))


@router.post("/retrieve-batch")
def evaluation_retrieve_batch(
    body: dict[str, Any],
    _principal: Principal = Depends(current_principal),
    container: AppContainer = Depends(get_container),
):
    queries = body.get("queries")
    if not isinstance(queries, list) or not queries:
        raise ValueError("评测问题列表不能为空")
    limit = min(max(1, int(body.get("limit", 10))), 50)
    prepared: list[tuple[str, str, str]] = []
    for index, item in enumerate(queries[:200]):
        if not isinstance(item, dict):
            raise ValueError("评测问题格式错误")
        question, crop = str(item.get("question", "")), str(item.get("crop", "AUTO"))
        prepared.append((str(item.get("id", index)), question, crop))

    def retrieve(item: tuple[str, str, str]) -> dict[str, Any]:
        item_id, question, crop = item
        return {"id": item_id, "bm25": container.agriculture.evaluation_retrieve(question, crop, limit)}

    with ThreadPoolExecutor(max_workers=min(4, len(prepared)), thread_name_prefix="agrigraph-eval") as executor:
        return envelope(list(executor.map(retrieve, prepared)))


@router.post("/control-relations-batch")
def evaluation_control_relations_batch(
    body: dict[str, Any],
    _principal: Principal = Depends(current_principal),
    container: AppContainer = Depends(get_container),
):
    raw_ids = body.get("diseaseIds")
    if not isinstance(raw_ids, list) or not raw_ids:
        raise ValueError("防治关系评测实体列表不能为空")
    disease_ids = [str(value).strip() for value in raw_ids if str(value).strip()]
    return envelope(container.agriculture.evaluation_control_relations(disease_ids))
