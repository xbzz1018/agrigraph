"""保留历史版本号；精简项目不再创建后台任务表。

Revision ID: 20260803_0002
Revises: 20260803_0001
Create Date: 2026-08-03
"""

from __future__ import annotations

from typing import Sequence

revision: str = "20260803_0002"
down_revision: str | None = "20260803_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
