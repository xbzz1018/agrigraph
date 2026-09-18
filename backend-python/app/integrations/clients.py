"""集中创建并关闭 Elasticsearch 与 Neo4j 客户端。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.settings import Settings
from app.integrations.retrieval import ElasticsearchRestClient


@dataclass(slots=True)
class ExternalClients:
    es: ElasticsearchRestClient
    neo4j: Any

    @classmethod
    def build(cls, settings: Settings) -> "ExternalClients":
        from neo4j import GraphDatabase

        auth = (settings.neo4j_username, settings.neo4j_password) if settings.neo4j_password else None
        neo4j = GraphDatabase.driver(
            settings.neo4j_url,
            auth=auth,
            connection_timeout=5,
            max_transaction_retry_time=0,
        )
        return cls(ElasticsearchRestClient(settings), neo4j)

    def close(self) -> None:
        self.es.close()
        self.neo4j.close()
