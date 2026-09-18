"""检查核心存储、检索服务和模型网关。"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from typing import Any

import httpx

from app.core.settings import Settings


class DependencyHealth:
    def __init__(
        self,
        settings: Settings,
        model_configured: bool,
        vision_configured: bool,
        embedding_configured: bool = False,
        reranker_configured: bool = False,
    ):
        self.settings = settings
        self.model_configured = model_configured
        self.vision_configured = vision_configured
        self.embedding_configured = embedding_configured
        self.reranker_configured = reranker_configured

    def check(self) -> dict[str, Any]:
        dependencies = {
            "sqlite": self._probe(self._sqlite),
            "elasticsearch": self._probe(self._elasticsearch),
            "neo4j": self._probe(self._neo4j) if self.settings.neo4j_password else "NOT_CONFIGURED",
            "postgresqlMemory": self._probe(self._postgresql)
            if self.settings.postgres_dsn
            else "NOT_CONFIGURED",
            "redisMemory": self._probe(self._redis) if self.settings.redis_url else "NOT_CONFIGURED",
            "deepseek": "CONFIGURED" if self.model_configured else "NOT_CONFIGURED",
            "qwen3Vl": "CONFIGURED" if self.vision_configured else "NOT_CONFIGURED",
            "bgeM3": "CONFIGURED" if self.embedding_configured else "NOT_CONFIGURED",
            "bgeReranker": "CONFIGURED" if self.reranker_configured else "NOT_CONFIGURED",
        }
        down = any(str(value).startswith("DOWN") for value in dependencies.values())
        return {"status": "DEGRADED" if down else "UP", "dependencies": dependencies}

    def _sqlite(self) -> None:
        with sqlite3.connect(self.settings.db_path, timeout=2) as db:
            db.execute("SELECT 1").fetchone()

    def _elasticsearch(self) -> None:
        auth = (self.settings.es_username, self.settings.es_password) if self.settings.es_username else None
        with httpx.Client(base_url=self.settings.es_url, auth=auth, timeout=2) as client:
            client.get("/").raise_for_status()

    def _neo4j(self) -> None:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            self.settings.neo4j_url,
            auth=(self.settings.neo4j_username, self.settings.neo4j_password),
            connection_timeout=2,
        )
        try:
            driver.verify_connectivity()
        finally:
            driver.close()

    def _postgresql(self) -> None:
        import psycopg

        with psycopg.connect(self.settings.postgres_dsn, connect_timeout=2) as connection:
            connection.execute("SELECT 1").fetchone()

    def _redis(self) -> None:
        import redis

        client = redis.Redis.from_url(
            self.settings.redis_url,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        try:
            client.ping()
        finally:
            client.close()

    @staticmethod
    def _probe(action: Callable[[], None]) -> str:
        try:
            action()
            return "UP"
        except Exception as exc:  # noqa: BLE001 - 健康接口必须汇总外部依赖异常
            return f"DOWN: {(str(exc).strip() or type(exc).__name__)[:180]}"
