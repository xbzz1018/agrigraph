"""从 FastAPI 应用状态中获取容器和当前登录身份。"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from app.core.container import AppContainer
from app.core.security import Principal


def get_container(request: Request) -> AppContainer:
    return request.app.state.container


async def current_principal(request: Request, container: AppContainer = Depends(get_container)) -> Principal:
    return await container.authenticator.authenticate(request.headers.get("Authorization"))


def require_admin(principal: Principal) -> None:
    if not principal.is_admin:
        raise HTTPException(status_code=403, detail="仅管理员可以执行该操作")
