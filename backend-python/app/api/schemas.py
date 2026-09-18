"""HTTP 请求模型；字段名保持与现有前端和公开 API 合同兼容。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """一次聊天、诊断或评测请求。"""

    question: str = Field(min_length=1, max_length=4000)
    cropScope: str = "AUTO"
    knowledgeEnhanced: bool = True
    requestId: str | None = None


class CreateSessionRequest(BaseModel):
    """创建农业对话会话。"""

    title: str = "新农业对话"
    cropScope: str = "AUTO"
    knowledgeEnhanced: bool = True


class UpdateSessionRequest(BaseModel):
    """按需更新会话展示名称和检索范围。"""

    title: str | None = None
    cropScope: str | None = None
    knowledgeEnhanced: bool | None = None


class UserCredentials(BaseModel):
    """注册与登录共用的用户名密码载荷。"""

    username: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=6, max_length=200)


class RefreshTokenRequest(BaseModel):
    """使用刷新令牌换取新访问令牌。"""

    refreshToken: str

