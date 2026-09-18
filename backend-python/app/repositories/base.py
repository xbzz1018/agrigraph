"""提供 SQLite 连接、WAL、外键、busy timeout 和 Alembic 初始化。"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from alembic import command
from alembic.config import Config


class SQLiteRepositoryBase:
    """所有领域仓储共享的连接与写事务锁。"""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._upgrade_schema()

    def connect(self) -> sqlite3.Connection:
        """创建短生命周期连接，并统一启用 SQLite 安全参数。"""

        connection = sqlite3.connect(self.path, timeout=5, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _upgrade_schema(self) -> None:
        """通过 Alembic 升级结构，避免应用层再维护一份建表 SQL。"""

        backend_root = Path(__file__).resolve().parents[2]
        config = Config(str(backend_root / "alembic.ini"))
        config.set_main_option("script_location", str(backend_root / "migrations"))
        config.attributes["agrigraph_db_path"] = self.path
        command.upgrade(config, "head")
