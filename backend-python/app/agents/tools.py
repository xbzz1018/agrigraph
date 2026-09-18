"""固定工作流使用的三个受控工具：会话、BM25 和 Neo4j。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Callable

from app.agents.schemas import Evidence
from app.core.settings import Settings
from app.integrations.retrieval import Bm25Retriever
from app.integrations.semantic import RerankerGateway
from app.repositories import Repository
from app.repositories.memory import LayeredMemory


class ToolPermissionError(PermissionError):
    pass


@dataclass(slots=True)
class ToolRegistry:
    settings: Settings
    repository: Repository
    retriever: Bm25Retriever | None = None
    graph_driver: Any | None = None
    reranker: RerankerGateway | None = None
    memory: LayeredMemory | None = None

    def __post_init__(self) -> None:
        if self.retriever is None:
            self.retriever = Bm25Retriever(self.settings)
        if self.reranker is None:
            self.reranker = RerankerGateway(self.settings)

    ALLOWLISTS = {
        "session-context": {"session.load"},
        "document-research": {"elasticsearch.bm25"},
        "graph-reasoning": {"neo4j.relations"},
    }

    def call(self, agent_id: str, tool_name: str, **kwargs: Any) -> list[dict[str, Any]]:
        if tool_name not in self.ALLOWLISTS.get(agent_id, set()):
            raise ToolPermissionError(f"{agent_id} cannot call {tool_name}")
        handlers: dict[str, Callable[..., list[dict[str, Any]]]] = {
            "session.load": self._session,
            "elasticsearch.bm25": self._documents,
            "neo4j.relations": self._relations,
        }
        return handlers[tool_name](**kwargs)

    def _session(
        self,
        owner: str,
        thread_id: str,
        current_objective: str,
        project_scope: str,
        limit: int = 6,
    ) -> list[dict[str, Any]]:
        memory_values: list[dict[str, Any]] = []
        if self.memory is not None:
            memory_values = self.memory.load_context(
                owner,
                thread_id,
                current_objective,
                project_scope,
                limit,
            )
        try:
            messages = self.repository.chats.recent_messages(owner, thread_id, limit + 1)
        except LookupError:
            messages = []
        if messages and messages[-1]["role"] == "user" and messages[-1]["content"].strip() == current_objective:
            messages = messages[:-1]
        long_limit = min(2, max(0, limit))
        long_term = (
            [item for item in memory_values if item.get("role") == "memory"][-long_limit:]
            if long_limit
            else []
        )
        redis_short = [item for item in memory_values if item.get("role") != "memory"]
        short_term = redis_short or messages
        remaining = max(0, limit - len(long_term))
        return [*long_term, *(short_term[-remaining:] if remaining else [])]

    def _documents(
        self,
        query: str,
        crop_scope: str,
        query_type: str = "ENTITY",
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = []
        values_by_id: dict[str, dict[str, Any]] = {}
        use_reranker = (
            query_type.upper() in {"SYMPTOM", "CONDITION"}
            and self.reranker is not None
            and self.reranker.enabled
        )
        candidate_limit = (
            self.settings.reranker_candidate_limit
            if use_reranker
            else max(limit, 10)
        )
        search_hits = self.retriever.search(query, crop_scope, candidate_limit)
        for hit in search_hits:
            source = hit.get("_source", {})
            entity_id = str(source.get("id") or source.get("entityId") or hit.get("_id") or "")
            values_by_id[entity_id] = {"hit": hit, "source": source}
        # 图片/症状问答优先保留名称精确命中的实体，避免同症状病害挤掉图片所属候选。
        for term in (query,):
            exact = self.retriever.raw_search(
                {
                    "bool": {
                        "should": [
                            {"term": {"name.keyword": term}},
                            {"match_phrase": {"name": term}},
                        ],
                        "minimum_should_match": 1,
                    }
                },
                min(limit, 10),
            )
            for hit in exact:
                source = hit.get("_source", {})
                entity_id = str(source.get("id") or source.get("entityId") or hit.get("_id") or "")
                hit["_score"] = 1.0
                hit["_retrieval"] = {
                    "mode": "bm25_exact",
                    "rank": len(values_by_id) + 1,
                    "degraded": False,
                    "reason": "",
                }
                values_by_id.setdefault(entity_id, {"hit": hit, "source": source})
        candidates = [item["hit"] for item in values_by_id.values()]
        ranked_hits = (
            self.reranker.rerank(query, candidates, limit)
            if use_reranker and self.reranker is not None
            else candidates[:limit]
        )
        for hit in ranked_hits:
            source = hit.get("_source", {})
            entity_id = str(source.get("id") or source.get("entityId") or hit.get("_id") or "")
            name = str(source.get("name") or source.get("title") or "农业知识")
            excerpts = [
                str(source.get(key, "")).strip()
                for key in ("summary", "symptoms", "pathogen", "occurrenceFactors")
                if source.get(key)
            ]
            option_names = [
                str(item.get("name", ""))
                for item in source.get("controlOptions", [])
                if isinstance(item, dict) and item.get("name")
            ]
            if option_names:
                excerpts.append("防治选项：" + "、".join(option_names))
            if source.get("controlPrinciples"):
                excerpts.append("安全防治原则：" + str(source["controlPrinciples"]))
            values.append(
                Evidence(
                    id=f"doc:{entity_id}",
                    source_type="document",
                    title=name,
                    excerpt="\n".join(excerpts)[:2400],
                    score=float(hit.get("_score") or 0),
                    metadata={
                        "entity": {
                            "id": entity_id,
                            "name": name,
                            "crop": str(source.get("crop") or ""),
                            "type": str(source.get("entityTypeCode") or source.get("entityType") or ""),
                            "score": float(hit.get("_score") or 0),
                        },
                        "controlOptions": source.get("controlOptions", []),
                        "retrieval": hit.get("_retrieval", {}),
                    },
                ).model_dump()
            )
        return values

    def _relations(self, query: str, entity_ids: list[str], limit: int = 20) -> list[dict[str, Any]]:
        cypher = """
        MATCH (n)-[r]-(m)
        WHERE n.id IN $ids
           OR toLower(coalesce(n.label,n.entityName,'')) CONTAINS toLower($query)
           OR toLower($query) CONTAINS toLower(coalesce(n.label,n.entityName,''))
        WITH n,r,m, CASE WHEN type(r)='RELATED_TO' THEN r.type ELSE type(r) END AS relation
        WHERE relation IN ['HAS_SYMPTOM','CAUSED_BY','FAVORED_BY','CONTROLS','PREVENTS']
        WITH r, relation, startNode(r) AS sourceNode, endNode(r) AS targetNode
        RETURN coalesce(sourceNode.label,sourceNode.entityName,sourceNode.id) AS source,
               sourceNode.id AS sourceId, relation,
               coalesce(targetNode.label,targetNode.entityName,targetNode.id) AS target,
               targetNode.id AS targetId,
               coalesce(r.evidence,'') AS evidence
        LIMIT $limit
        """
        records = self.graph_driver.execute_query(
            cypher,
            parameters_={"query": query[:120], "ids": entity_ids[:10], "limit": min(max(1, limit), 50)},
        ).records
        values = []
        for record in records:
            source, relation, target = str(record["source"]), str(record["relation"]), str(record["target"])
            values.append(
                Evidence(
                    id=f"graph:{hashlib.sha256(f'{source}:{relation}:{target}'.encode()).hexdigest()[:16]}",
                    source_type="graph",
                    title=f"{source} - {relation} - {target}",
                    excerpt=f"{source} 通过 {relation} 关联 {target}",
                    score=0.8,
                    metadata={
                        "sourceId": str(record.get("sourceId") or ""),
                        "source": source,
                        "relation": relation,
                        "targetId": str(record.get("targetId") or ""),
                        "target": target,
                    },
                ).model_dump()
            )
        return values
