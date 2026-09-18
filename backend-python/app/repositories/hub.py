"""将领域仓储装配为一个依赖对象，同时保留迁移期的直接方法调用。"""

from __future__ import annotations

from app.repositories.agent_runs import AgentRunsRepositoryMixin
from app.repositories.base import SQLiteRepositoryBase
from app.repositories.chats import ChatsRepositoryMixin
from app.repositories.users import UsersRepositoryMixin


class RepositoryHub(
    SQLiteRepositoryBase,
    UsersRepositoryMixin,
    ChatsRepositoryMixin,
    AgentRunsRepositoryMixin,
):
    """集中共享连接配置，并按属性向调用方展示业务边界。"""

    @property
    def users(self) -> UsersRepositoryMixin:
        return self

    @property
    def chats(self) -> ChatsRepositoryMixin:
        return self

    @property
    def runs(self) -> AgentRunsRepositoryMixin:
        return self

