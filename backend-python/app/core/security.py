"""提供 JWT 登录、刷新、撤销和 FastAPI 身份认证边界。"""

from __future__ import annotations

import base64
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import HTTPException

from app.core.settings import Settings
from app.repositories import Repository


@dataclass(frozen=True, slots=True)
class Principal:
    """通过认证后的最小用户身份。"""

    username: str
    role: str
    user_id: str | None = None

    @property
    def is_admin(self) -> bool:
        return self.role.upper() == "ADMIN"


class Authenticator:
    """验证访问令牌、撤销状态和角色声明。"""

    def __init__(self, settings: Settings, repository: Repository):
        self.settings = settings
        self.repository = repository

    async def authenticate(self, authorization: str | None = None) -> Principal:
        """校验已由 API 层提取出的 Bearer Token，并返回当前身份。"""
        if not self.settings.auth_required:
            return Principal("local-developer", "ADMIN", "local")
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="缺少登录令牌")
        if not self.settings.jwt_secret:
            raise HTTPException(status_code=503, detail="服务端未配置 PAISMART_JWT_SECRET")
        try:
            secret = base64.b64decode(self.settings.jwt_secret)
            claims = jwt.decode(authorization[7:], secret, algorithms=["HS256"])
        except Exception as exc:
            raise HTTPException(status_code=401, detail="登录令牌无效或已过期") from exc
        token_id = claims.get("tokenId")
        if not token_id:
            raise HTTPException(status_code=401, detail="登录令牌缺少 tokenId")
        if claims.get("type") == "refresh":
            raise HTTPException(status_code=401, detail="不能使用刷新令牌访问业务接口")
        if not self.repository.users.token_active(str(token_id), "access"):
            raise HTTPException(status_code=401, detail="登录令牌已注销")
        return Principal(str(claims.get("sub", "")), str(claims.get("role", "USER")), claims.get("userId"))


class TokenManager:
    """负责注册、登录、刷新及令牌撤销持久化。"""

    def __init__(self, settings: Settings, repository: Repository):
        self.settings, self.repository = settings, repository

    def register(self, username: str, password: str, role: str = "USER") -> dict[str, object]:
        encoded = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")
        return self.repository.users.create_user(username, encoded, role)

    def reset_password(
        self, username: str, password: str, role: str | None = None, *, create: bool = False
    ) -> dict[str, object]:
        normalized_role = role.upper() if role else None
        if normalized_role not in {None, "USER", "ADMIN"}:
            raise ValueError("Role must be USER or ADMIN")
        try:
            user = self.repository.users.get_user(username)
        except LookupError:
            if not create:
                raise
            created = self.register(username, password, normalized_role or "USER")
            return {**created, "action": "created"}

        encoded = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")
        updated = self.repository.users.update_password(username, encoded, normalized_role)
        self.repository.users.revoke_user_tokens(str(user["id"]))
        return {**updated, "action": "updated"}

    def login(self, username: str, password: str) -> dict[str, str]:
        try:
            user = self.repository.users.get_user(username)
        except LookupError as exc:
            raise ValueError("Invalid username or password") from exc
        if not bcrypt.checkpw(password.encode("utf-8"), user["password"].encode("ascii")):
            raise ValueError("Invalid username or password")
        return self._pair(user)

    def refresh(self, refresh_token: str) -> dict[str, str]:
        claims = self._decode(refresh_token)
        refresh_id = str(claims.get("refreshTokenId", ""))
        if claims.get("type") != "refresh" or not self.repository.users.token_active(refresh_id, "refresh"):
            raise ValueError("Invalid refresh token")
        user = self.repository.users.get_user(str(claims["sub"]))
        self.repository.users.revoke_token(refresh_id)
        return self._pair(user)

    def logout(self, token: str) -> None:
        claims = self._decode(token)
        token_id = claims.get("tokenId") or claims.get("refreshTokenId")
        if token_id:
            self.repository.users.revoke_token(str(token_id))

    def logout_all(self, user_id: str) -> None:
        self.repository.users.revoke_user_tokens(user_id)

    def _pair(self, user: dict[str, object]) -> dict[str, str]:
        now = datetime.now(timezone.utc)
        access_id, refresh_id = str(uuid.uuid4()), str(uuid.uuid4())
        common = {
            "sub": user["username"],
            "role": user["role"],
            "userId": str(user["id"]),
        }
        access_exp, refresh_exp = now + timedelta(hours=1), now + timedelta(days=7)
        access = self._encode({**common, "tokenId": access_id, "exp": access_exp})
        refresh = self._encode(
            {
                "sub": user["username"],
                "userId": str(user["id"]),
                "type": "refresh",
                "refreshTokenId": refresh_id,
                "exp": refresh_exp,
            }
        )
        self.repository.users.save_token(
            access_id, str(user["id"]), str(user["username"]), "access", access_exp.isoformat()
        )
        self.repository.users.save_token(
            refresh_id, str(user["id"]), str(user["username"]), "refresh", refresh_exp.isoformat()
        )
        return {"token": access, "refreshToken": refresh}

    def _encode(self, claims: dict[str, object]) -> str:
        return jwt.encode(claims, self._secret(), algorithm="HS256")

    def _decode(self, token: str) -> dict[str, object]:
        try:
            return jwt.decode(token, self._secret(), algorithms=["HS256"])
        except Exception as exc:
            raise ValueError("Invalid token") from exc

    def _secret(self) -> bytes:
        if not self.settings.jwt_secret:
            raise RuntimeError("服务端未配置 PAISMART_JWT_SECRET")
        return base64.b64decode(self.settings.jwt_secret)
