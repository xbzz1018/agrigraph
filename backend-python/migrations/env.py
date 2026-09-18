"""Alembic 运行环境：解析项目级 SQLite 路径并启用外键和锁等待。"""

from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

backend_root = Path(__file__).resolve().parents[1]
project_root = backend_root.parent
configured_path = config.attributes.get("agrigraph_db_path")
if configured_path:
    db_path = Path(configured_path).resolve()
else:
    raw_path = Path(os.getenv("AGRIGRAPH_DB_PATH", "var/agrigraph.db"))
    db_path = raw_path if raw_path.is_absolute() else (project_root / raw_path).resolve()
db_path.parent.mkdir(parents=True, exist_ok=True)
config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    # SQLAlchemy 2 的普通 connect() 不会自动提交版本表 DML；begin() 保证迁移版本与 DDL 一起落盘。
    with connectable.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.exec_driver_sql("PRAGMA busy_timeout=5000")
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
