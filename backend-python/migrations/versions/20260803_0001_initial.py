"""创建 Python 主后端的初始业务与审计结构。

Revision ID: 20260803_0001
Revises:
Create Date: 2026-08-03
"""

from __future__ import annotations

from typing import Sequence

from alembic import op

from migrations.initial_schema import INITIAL_SCHEMA

revision: str = "20260803_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    for statement in (part.strip() for part in INITIAL_SCHEMA.split(";")):
        if statement:
            connection.exec_driver_sql(statement)


def downgrade() -> None:
    # Operational data is intentionally preserved. Rollbacks use a backup or a
    # forward migration instead of dropping user conversations and audit trails.
    pass
