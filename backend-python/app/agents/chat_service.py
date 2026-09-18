"""将固定 LangGraph 状态流转换为运行审计和公开 SSE。"""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterator
from typing import Any

from app.agents.chat_graph import MainAgentGraph
from app.agents.schemas import AgentEvent, AgentRunResult, AgentState
from app.api.schemas import ChatRequest
from app.repositories import Repository
from app.repositories.memory import LayeredMemory


class AgentService:
    def __init__(
        self,
        repository: Repository,
        graph: MainAgentGraph,
        memory: LayeredMemory | None = None,
    ):
        self.repository = repository
        self.graph = graph
        self.memory = memory

    def stream_chat(self, owner: str, session_id: str, request: ChatRequest) -> Iterator[tuple[str, dict[str, Any]]]:
        session = self.repository.chats.get_session_summary(owner, session_id)
        self.repository.chats.update_session(
            owner,
            session_id,
            crop_scope=self._scope(request.cropScope),
            enhanced=request.knowledgeEnhanced,
            title=request.question[:35] if session["title"] == "新农业对话" else session["title"],
        )
        self.repository.chats.add_message(session_id, "user", request.question.strip())
        self.remember_message(owner, session_id, "user", request.question)
        saved = None
        for event, payload in self.stream_run(owner, session_id, request):
            if event == "complete":
                saved = self.repository.chats.add_message(session_id, "assistant", payload["answer"], payload)
                self.remember_message(owner, session_id, "assistant", payload["answer"])
                self.remember_interaction(owner, session_id, request.question, payload)
            yield event, payload
        if saved is not None:
            yield "message_saved", saved

    def stream_run(
        self,
        owner: str,
        thread_id: str,
        request: ChatRequest,
        request_type: str = "chat",
        vision_observation: dict[str, Any] | None = None,
    ) -> Iterator[tuple[str, dict[str, Any]]]:
        run_id = request.requestId or str(uuid.uuid4())
        started = time.perf_counter()
        self.repository.runs.create_run(
            run_id, owner, thread_id, request_type, request.question.strip(), self._scope(request.cropScope)
        )
        yield "connected", {"requestId": run_id, "agentRunId": run_id}
        initial: AgentState = {
            "run_id": run_id,
            "thread_id": thread_id,
            "owner_username": owner,
            "request_type": request_type,
            "objective": request.question.strip(),
            "crop_scope": self._scope(request.cropScope),
            "knowledge_enhanced": request.knowledgeEnhanced,
            "vision_observation": vision_observation or {},
            "document_evidence": [],
            "graph_evidence": [],
            "memory_context": [],
            "candidate_entities": [],
            "control_options": [],
            "warnings": [],
            "workflow": [],
            "events": [],
            "model_calls": 0,
            "model_usage": {},
            "tool_calls": 0,
        }
        last_state: AgentState = initial
        emitted = 0
        try:
            config = {"configurable": {"thread_id": run_id}, "recursion_limit": 24}
            for state in self.graph.graph.stream(initial, config=config, stream_mode="values"):
                last_state = state
                if time.perf_counter() - started > self.graph.runtime.settings.run_timeout_seconds:
                    raise TimeoutError("Workflow run timeout")
                if self.repository.runs.run_status(run_id) == "CANCEL_REQUESTED":
                    raise RuntimeError("CANCELED")
                events = state.get("events", [])
                for raw in events[emitted:]:
                    event = self.repository.runs.save_event(AgentEvent.model_validate(raw))
                    yield "workflow", {
                        "type": event.agent_id,
                        "label": event.label,
                        "data": event.data_summary,
                        "timestamp": event.timestamp,
                    }
                emitted = len(events)
            duration = int((time.perf_counter() - started) * 1000)
            result = self._result(last_state, run_id, duration)
            self.repository.runs.finish_run(run_id, "COMPLETED", result, duration)
            yield "retrieval_result", {
                "candidateCount": len(result["candidateEntities"]),
                "citationCount": len(result["citations"]),
                "graphRelationCount": len(result["graphRelations"]),
                "mode": "bm25",
            }
            for chunk in self._chunks(result["answer"]):
                yield "answer_chunk", {"data": chunk}
            yield "complete", result
        except Exception as exc:
            duration = int((time.perf_counter() - started) * 1000)
            result = self._result(last_state, run_id, duration)
            self.repository.runs.finish_run(run_id, "FAILED", result, duration, type(exc).__name__)
            yield "error", {"code": type(exc).__name__, "message": "农业知识工作流执行失败", "runId": run_id}

    def run(
        self,
        owner: str,
        thread_id: str,
        request: ChatRequest,
        request_type: str = "chat",
        vision_observation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = None
        error = None
        for event, payload in self.stream_run(owner, thread_id, request, request_type, vision_observation):
            if event == "complete":
                result = payload
            elif event == "error":
                error = payload
        if result is None:
            raise RuntimeError((error or {}).get("message", "农业知识工作流执行失败"))
        return result

    def cancel(self, run_id: str, owner: str, admin: bool = False) -> dict[str, Any]:
        run = self.repository.runs.get_run(run_id, owner, admin)
        if run["status"] != "RUNNING":
            return {"runId": run_id, "status": run["status"], "cancelled": False}
        self.repository.runs.update_run_status(run_id, "CANCEL_REQUESTED")
        return {"runId": run_id, "status": "CANCEL_REQUESTED", "cancelled": True}

    def replay(self, run_id: str, principal: str) -> dict[str, Any]:
        run = self.repository.runs.get_run(run_id, principal, admin=True)
        request = ChatRequest(question=run["objective"], cropScope=run["cropScope"], knowledgeEnhanced=True)
        return self.run(principal, run["threadId"], request, run["requestType"])

    def remember_message(self, owner: str, session_id: str, role: str, content: str) -> None:
        if self.memory is not None:
            self.memory.remember_message(owner, session_id, role, content)

    def remember_interaction(
        self,
        owner: str,
        session_id: str,
        question: str,
        result: dict[str, Any],
    ) -> None:
        if self.memory is not None:
            self.memory.remember_interaction(
                owner,
                session_id,
                self.graph.runtime.settings.memory_project_scope,
                question,
                result,
            )

    def forget_session(self, owner: str, session_id: str) -> None:
        if self.memory is not None:
            self.memory.forget_session(owner, session_id)

    def _result(self, state: AgentState, run_id: str, duration: int) -> dict[str, Any]:
        citation_ids = set(state.get("citation_ids", []))
        documents = state.get("document_evidence", [])
        graph = state.get("graph_evidence", [])
        result = AgentRunResult(
            answer=state.get("final_answer") or state.get("draft_answer") or "当前无法生成回答。",
            candidateEntities=state.get("candidate_entities", []),
            claims=state.get("draft_claims", []),
            citations=[
                {
                    "id": item["id"],
                    "title": item["title"],
                    "excerpt": item["excerpt"],
                    "score": item["score"],
                    "url": item.get("uri"),
                }
                for item in documents
                if item.get("id") in citation_ids
            ],
            graphRelations=[item.get("metadata", {}) for item in graph if item.get("metadata")],
            controlOptions=state.get("control_options", []),
            warnings=list(dict.fromkeys(state.get("warnings", []))),
            latencyMs=duration,
            observation=state.get("vision_observation") or None,
            agentRunId=run_id,
            workflow=list(dict.fromkeys(state.get("workflow", []))),
            tokenUsage=state.get("model_usage", {}),
        )
        return result.model_dump()

    @staticmethod
    def _chunks(value: str, size: int = 80) -> Iterator[str]:
        for offset in range(0, len(value), size):
            yield value[offset : offset + size]

    @staticmethod
    def _scope(value: str) -> str:
        normalized = (value or "AUTO").strip().upper()
        return normalized if normalized in {"AUTO", "TOMATO", "RICE"} else value.strip()[:40] or "AUTO"
