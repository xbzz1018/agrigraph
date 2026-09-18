"""图片症状理解接口：临时图片不会持久化，观察结果复用统一知识工作流。"""

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import current_principal, get_container
from app.api.responses import envelope
from app.api.schemas import ChatRequest
from app.core.container import AppContainer
from app.core.security import Principal

router = APIRouter(prefix="/api/v1", tags=["diagnosis"])


@router.post("/diagnosis/image")
async def diagnose(
    image: UploadFile = File(...),
    crop: str = "未知",
    principal: Principal = Depends(current_principal),
    container: AppContainer = Depends(get_container),
):
    if not container.vision.enabled:
        raise HTTPException(status_code=503, detail="视觉模型未配置")
    if image.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=400, detail="仅支持 JPEG、PNG 或 WebP 图片")
    suffix = Path(image.filename or "image.jpg").suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        suffix = ".jpg"
    temp_dir = container.settings.db_path.parent / "diagnosis-inputs"
    temp_dir.mkdir(parents=True, exist_ok=True)
    image_path = temp_dir / f"{uuid.uuid4().hex}{suffix}"
    try:
        with image_path.open("wb") as target:
            shutil.copyfileobj(image.file, target)
        if image_path.stat().st_size > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="图片不能超过 10 MB")
        observation = await run_in_threadpool(container.vision.analyze, image_path, crop)
        if observation.crop == "未知" and crop in {"番茄", "水稻"}:
            observation = observation.model_copy(update={"crop": crop})
        terms = "、".join([*observation.plantParts, *observation.symptoms]) or "未提取到明确可见症状"
        request = ChatRequest(
            question=f"{observation.crop}图片可见特征：{terms}。请召回候选病虫害并说明知识依据。",
            cropScope=observation.crop,
        )
        result = await run_in_threadpool(
            container.agent_service.run,
            principal.username,
            str(uuid.uuid4()),
            request,
            "image",
            observation.model_dump(),
        )
        matched = await run_in_threadpool(container.agriculture.image_case_candidates, image_path, 3)
        if matched:
            known = {str(item.get("id")) for item in matched}
            result["candidateEntities"] = matched + [
                item for item in result.get("candidateEntities", []) if str(item.get("id")) not in known
            ]
            result["candidateEntities"] = result["candidateEntities"][:10]
        result["observation"] = observation.model_dump()
        return envelope(result)
    finally:
        image_path.unlink(missing_ok=True)
