"""Agent 运行列表、详情、事件、取消和回放接口。"""

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import current_principal, get_container
from app.api.responses import envelope
from app.core.container import AppContainer
from app.core.security import Principal

router = APIRouter(prefix="/api/v1", tags=["agent-runs"])


@router.get("/agent-runs")
def runs(
    status: str | None = None,
    principal: Principal = Depends(current_principal),
    container: AppContainer = Depends(get_container),
):
    return envelope(container.repositories.runs.list_runs(principal.username, principal.is_admin, status))


@router.get("/agent-runs/{run_id}")
def run_detail(
    run_id: str,
    principal: Principal = Depends(current_principal),
    container: AppContainer = Depends(get_container),
):
    return envelope(container.repositories.runs.get_run(run_id, principal.username, principal.is_admin))


@router.get("/agent-runs/{run_id}/events")
def run_events(
    run_id: str,
    afterSequence: int = 0,
    principal: Principal = Depends(current_principal),
    container: AppContainer = Depends(get_container),
):
    return envelope(container.repositories.runs.events(run_id, principal.username, afterSequence, principal.is_admin))


@router.post("/agent-runs/{run_id}/cancel")
def cancel(
    run_id: str,
    principal: Principal = Depends(current_principal),
    container: AppContainer = Depends(get_container),
):
    return envelope(container.agent_service.cancel(run_id, principal.username, principal.is_admin))


@router.post("/agent-runs/{run_id}/replay")
def replay(
    run_id: str,
    principal: Principal = Depends(current_principal),
    container: AppContainer = Depends(get_container),
):
    if not principal.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可以回放 Agent 运行")
    return envelope(container.agent_service.replay(run_id, principal.username))
