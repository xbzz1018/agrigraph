"""Elasticsearch BM25 候选检索。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from app.core.settings import Settings


class Bm25Retriever:
    """使用单一、可解释的 BM25 策略召回病虫害与知识证据。"""

    def __init__(
        self,
        settings: Settings,
        client_factory: Callable[[], Any] | None = None,
        client: Any | None = None,
    ):
        self.settings = settings
        self._client_factory = client_factory
        self._client_instance = client or (None if client_factory else ElasticsearchRestClient(settings))
        self._owns_client = client is None and client_factory is None

    def search(self, query: str, crop_scope: str = "AUTO", limit: int = 10) -> list[dict[str, Any]]:
        must = []
        should = [
            {
                "multi_match": {
                    "query": query[:2000],
                    "fields": [
                        "name^8",
                        "title^6",
                        "aliases^5",
                        "symptoms^4",
                        "affectedParts^3",
                        "pathogen^3",
                        "occurrenceFactors^3",
                        "content",
                    ],
                    "type": "best_fields",
                }
            },
            {"match_phrase": {"symptoms": {"query": query[:800], "boost": 3}}},
            {"match_phrase": {"content": {"query": query[:800], "boost": 1.5}}},
        ]
        filters = self._crop_filters(crop_scope)
        hits = self._search(query={"bool": {"must": must, "should": should, "minimum_should_match": 1, "filter": filters}}, size=min(max(1, limit), 100))
        maximum = max((float(hit.get("_score") or 0) for hit in hits), default=1.0) or 1.0
        return [self._public_hit(hit, float(hit.get("_score") or 0) / maximum, rank) for rank, hit in enumerate(hits, 1)]

    def raw_search(self, query: dict[str, Any], size: int, offset: int = 0) -> list[dict[str, Any]]:
        return self._search(query=query, size=min(max(1, size), 100), offset=max(0, offset))

    def _search(self, *, query: dict[str, Any], size: int, offset: int = 0) -> list[dict[str, Any]]:
        client = self._client()
        try:
            response = client.search(index=self.settings.es_index, query=query, size=size, from_=offset)
            return list(response.get("hits", {}).get("hits", []))
        except Exception:
            return []
        finally:
            if self._client_factory is not None:
                client.close()

    def _client(self) -> Any:
        return self._client_factory() if self._client_factory is not None else self._client_instance

    @staticmethod
    def _crop_filters(crop_scope: str) -> list[dict[str, Any]]:
        if crop_scope.upper() in {"", "AUTO"}:
            return []
        aliases = {"TOMATO": "番茄", "RICE": "水稻"}
        return [{"term": {"crop": aliases.get(crop_scope.upper(), crop_scope)}}]

    @staticmethod
    def _public_hit(hit: dict[str, Any], score: float, rank: int) -> dict[str, Any]:
        source = dict(hit.get("_source", {}))
        source.pop("vector", None)
        source.pop("embedding", None)
        return {
            **hit,
            "_score": min(1.0, max(0.0, score)),
            "_source": source,
            "_retrieval": {"mode": "bm25", "rank": rank, "degraded": False, "reason": ""},
        }

    def close(self) -> None:
        if self._owns_client and self._client_instance is not None:
            self._client_instance.close()


class ElasticsearchRestClient:
    """复用一个同步 httpx 连接池访问 Elasticsearch。"""

    def __init__(self, settings: Settings):
        auth = (settings.es_username, settings.es_password) if settings.es_username else None
        self._client = httpx.Client(base_url=settings.es_url, auth=auth, timeout=5)

    def search(self, **kwargs: Any) -> dict[str, Any]:
        index = kwargs.pop("index")
        body = {"size": kwargs.pop("size", 10), "from": kwargs.pop("from_", 0), **kwargs}
        response = self._client.post(f"/{index}/_search", json=body)
        response.raise_for_status()
        return response.json()

    def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        allow_not_found: bool = False,
    ) -> dict[str, Any] | None:
        response = self._client.request(method, path, json=json)
        if allow_not_found and response.status_code == 404:
            return None
        response.raise_for_status()
        if not response.content:
            return {}
        return response.json()

    def close(self) -> None:
        self._client.close()
