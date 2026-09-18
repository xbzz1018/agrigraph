"""按业务域拆分的 SQLite 仓储。"""

from app.repositories.hub import RepositoryHub

# 旧名称保留为内部迁移别名；新增代码优先使用 RepositoryHub。
Repository = RepositoryHub

__all__ = ["Repository", "RepositoryHub"]
