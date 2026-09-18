"""AgriGraph FastAPI 应用入口；这里只负责装配，不承载具体业务路由。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.responses import envelope
from app.api.routers import (
    agent_runs,
    agriculture,
    auth,
    chat,
    diagnosis,
    evaluation,
    health,
)
from app.core.container import AppContainer
from app.core.settings import Settings

ROUTERS = (
    health.router,
    auth.router,
    chat.router,
    diagnosis.router,
    agent_runs.router,
    agriculture.router,
    evaluation.router,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    """创建独立应用实例，便于测试注入临时数据库和受控配置。"""

    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env.ai", override=False)
    container = AppContainer.build(settings or Settings.from_env())

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        container.close()

    app = FastAPI(title="AgriGraph 农业病虫害多模态知识服务 API", version="2.0.0", lifespan=lifespan)
    app.state.container = container
    # 保留测试和已有扩展使用的状态名称；真实对象只由 container 创建一次。
    app.state.settings = container.settings
    app.state.repository = container.repositories
    app.state.agent_service = container.agent_service
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:9627", "http://localhost:9627"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["New-Token"],
    )

    @app.exception_handler(LookupError)
    async def lookup_error(_: Request, exc: LookupError):
        return JSONResponse(envelope(None, str(exc), 404), status_code=404)

    @app.exception_handler(ValueError)
    async def value_error(_: Request, exc: ValueError):
        return JSONResponse(envelope(None, str(exc), 400), status_code=400)

    for router in ROUTERS:
        app.include_router(router)
    return app


app = create_app()
