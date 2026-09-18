"""BGE-M3 Embedding 与 BGE-Reranker 外部推理边界。"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.settings import Settings


def _headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


class EmbeddingGateway:
    """调用 OpenAI 兼容 Embedding 服务；未配置时保持禁用。"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = (
            httpx.Client(
                headers=_headers(settings.embedding_api_key),
                timeout=settings.embedding_timeout_seconds,
            )
            if settings.embedding_api_base
            else None
        )

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self._client is None or not texts:
            return []
        response = self._client.post(
            f"{self.settings.embedding_api_base.rstrip('/')}/embeddings",
            json={"model": self.settings.embedding_model, "input": [text[:8000] for text in texts]},
        )
        response.raise_for_status()
        values = response.json().get("data", [])
        ordered = sorted(values, key=lambda item: int(item.get("index", 0)))
        embeddings = [[float(value) for value in item.get("embedding", [])] for item in ordered]
        if len(embeddings) != len(texts):
            raise ValueError("Embedding response count does not match input count")
        if any(len(value) != self.settings.embedding_dimensions for value in embeddings):
            raise ValueError("Embedding response dimensions do not match configured dimensions")
        return embeddings

    def close(self) -> None:
        if self._client is not None:
            self._client.close()


class RerankerGateway:
    """对 BM25 候选执行二阶段重排；异常时显式回退原始顺序。"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = (
            httpx.Client(
                headers=_headers(settings.reranker_api_key),
                timeout=settings.reranker_timeout_seconds,
            )
            if settings.reranker_api_base
            else None
        )

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def rerank(self, query: str, hits: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        if not hits:
            return []
        if self._client is None:
            return hits[:limit]
        documents = [self._document(hit) for hit in hits]
        try:
            response = self._client.post(
                f"{self.settings.reranker_api_base.rstrip('/')}/rerank",
                json={
                    "model": self.settings.reranker_model,
                    "query": query[:2000],
                    "documents": documents,
                    "top_n": min(limit, len(documents)),
                },
            )
            response.raise_for_status()
            body = response.json()
            results = body.get("results") or body.get("data") or body.get("output", {}).get("results") or []
            ranked: list[dict[str, Any]] = []
            for rank, item in enumerate(results, 1):
                index = int(item.get("index", item.get("document_index", -1)))
                if index < 0 or index >= len(hits):
                    continue
                score = float(item.get("relevance_score", item.get("score", 0.0)))
                hit = dict(hits[index])
                retrieval = dict(hit.get("_retrieval", {}))
                retrieval.update(
                    {
                        "mode": "bm25_rerank",
                        "bm25Rank": int(retrieval.get("rank", index + 1)),
                        "rank": rank,
                        "rerankerModel": self.settings.reranker_model,
                        "degraded": False,
                        "reason": "",
                    }
                )
                hit["_score"] = min(1.0, max(0.0, score))
                hit["_retrieval"] = retrieval
                ranked.append(hit)
            if ranked:
                return ranked[:limit]
            return self._fallback(hits, limit, "RERANK_EMPTY")
        except Exception:
            return self._fallback(hits, limit, "RERANK_FAILED")

    @staticmethod
    def _document(hit: dict[str, Any]) -> str:
        source = hit.get("_source", {})
        parts = [
            str(source.get(key, "")).strip()
            for key in ("name", "aliases", "symptoms", "pathogen", "occurrenceFactors", "content")
            if source.get(key)
        ]
        return "\n".join(parts)[:6000]

    @staticmethod
    def _fallback(hits: list[dict[str, Any]], limit: int, reason: str) -> list[dict[str, Any]]:
        values = []
        for hit in hits[:limit]:
            value = dict(hit)
            retrieval = dict(value.get("_retrieval", {}))
            retrieval.update({"degraded": True, "reason": reason})
            value["_retrieval"] = retrieval
            values.append(value)
        return values

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
