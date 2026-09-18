"""后端测试共享夹具：为每个用例提供隔离的 SQLite 与 checkpoint。"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from app.core.settings import Settings
from app.repositories import Repository


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return replace(
        Settings.from_env(),
        db_path=tmp_path / "agrigraph.db",
        checkpoint_db_path=tmp_path / "checkpoints.db",
        data_root=tmp_path / "datasets",
        auth_required=False,
        gateway_api_key="",
        vision_api_base="",
        vision_api_key="",
        vision_model="",
        es_url="http://127.0.0.1:1",
        neo4j_url="bolt://127.0.0.1:1",
    )


@pytest.fixture
def repository(settings: Settings) -> Repository:
    return Repository(settings.db_path)
