"""注册、登录、令牌刷新和退出接口。"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.api.dependencies import current_principal, get_container
from app.api.responses import envelope
from app.api.schemas import RefreshTokenRequest, UserCredentials
from app.core.container import AppContainer
from app.core.security import Principal

router = APIRouter(prefix="/api/v1", tags=["auth"])


@router.post("/users/register")
def register(body: UserCredentials, container: AppContainer = Depends(get_container)):
    container.token_manager.register(body.username.strip(), body.password)
    return envelope(message="User registered successfully")


@router.post("/users/login")
def login(body: UserCredentials, container: AppContainer = Depends(get_container)):
    return envelope(container.token_manager.login(body.username.strip(), body.password), "Login successful")


@router.post("/auth/refreshToken")
def refresh_token(body: RefreshTokenRequest, container: AppContainer = Depends(get_container)):
    return envelope(container.token_manager.refresh(body.refreshToken), "Token refreshed successfully")


@router.get("/auth/error")
def custom_backend_error(code: int, msg: str):
    safe_code = min(max(code, 400), 599)
    return JSONResponse({"code": safe_code, "message": msg}, status_code=safe_code)


@router.get("/users/me")
def current_user(
    principal: Principal = Depends(current_principal),
    container: AppContainer = Depends(get_container),
):
    return envelope(container.repositories.users.user_view(principal.username), "Get user detail successful")


@router.post("/users/logout")
def logout(
    request: Request,
    _principal: Principal = Depends(current_principal),
    container: AppContainer = Depends(get_container),
):
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        container.token_manager.logout(authorization[7:])
    return envelope(message="Logout successful")


@router.post("/users/logout-all")
def logout_all(
    principal: Principal = Depends(current_principal),
    container: AppContainer = Depends(get_container),
):
    container.token_manager.logout_all(principal.user_id or "")
    return envelope(message="Logout from all devices successful")
