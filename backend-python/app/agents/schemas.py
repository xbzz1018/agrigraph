"""固定农业知识工作流的共享状态、事件和公开响应。"""

from __future__ import annotations

import operator
from datetime import datetime, timezone
from typing import Annotated, Any, Literal, TypedDict

from pydantic import BaseModel, Field


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Evidence(BaseModel):
    id: str
    source_type: Literal["document", "graph", "memory"]
    title: str
    excerpt: str
    score: float = Field(ge=0, le=1)
    uri: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentEvent(BaseModel):
    sequence: int = 0
    run_id: str
    step_id: str
    agent_id: str
    event_type: Literal["started", "completed", "failed", "skipped", "tool"]
    status: str
    label: str
    timestamp: str = Field(default_factory=utc_now)
    duration_ms: int | None = None
    data_summary: dict[str, Any] = Field(default_factory=dict)


class AgentState(TypedDict, total=False):
    run_id: str
    thread_id: str
    owner_username: str
    request_type: str
    objective: str
    crop_scope: str
    knowledge_enhanced: bool
    vision_observation: dict[str, Any]
    agriculture_query: dict[str, Any]
    retrieval_query: str
    restricted_usage_request: bool
    document_evidence: list[dict[str, Any]]
    graph_evidence: list[dict[str, Any]]
    memory_context: list[dict[str, Any]]
    candidate_entities: list[dict[str, Any]]
    control_options: list[dict[str, Any]]
    draft_claims: list[dict[str, Any]]
    citation_ids: list[str]
    citation_coverage: float
    warnings: Annotated[list[str], operator.add]
    workflow: Annotated[list[str], operator.add]
    events: Annotated[list[dict[str, Any]], operator.add]
    draft_answer: str
    final_answer: str
    model_calls: Annotated[int, operator.add]
    model_usage: dict[str, Any]
    tool_calls: Annotated[int, operator.add]


class AgentRunResult(BaseModel):
    answer: str
    candidateEntities: list[dict[str, Any]] = Field(default_factory=list)
    claims: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    graphRelations: list[dict[str, Any]] = Field(default_factory=list)
    controlOptions: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    latencyMs: int = 0
    observation: dict[str, Any] | None = None
    agentRunId: str
    workflow: list[str] = Field(default_factory=list)
    tokenUsage: dict[str, Any] = Field(default_factory=dict)
    retrievalMode: Literal["bm25"] = "bm25"
