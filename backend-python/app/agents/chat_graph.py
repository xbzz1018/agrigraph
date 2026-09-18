"""编译固定农业知识工作流，并管理独立 checkpoint SQLite。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from app.agents.runtime import AgentRuntime
from app.agents.schemas import AgentState


class MainAgentGraph:
    def __init__(self, runtime: AgentRuntime, checkpoint_path: Path):
        self.runtime = runtime
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(checkpoint_path, check_same_thread=False)
        self._checkpointer = SqliteSaver(self._connection)
        self._checkpointer.setup()
        self.graph = self._build(runtime)

    def _build(self, runtime: AgentRuntime):
        builder = StateGraph(AgentState)
        builder.add_node("query_router", runtime.query_router)
        builder.add_node("session_context", runtime.session_context)
        builder.add_node("document_research", runtime.document_research)
        builder.add_node("graph_reasoning", runtime.graph_reasoning)
        builder.add_node("answer", runtime.answer)
        builder.add_node("evidence_check", runtime.evidence_check)
        builder.add_node("output_boundary", runtime.output_boundary)
        builder.add_node("finalize", runtime.finalize)
        builder.add_edge(START, "session_context")
        builder.add_edge("session_context", "query_router")
        builder.add_edge("query_router", "document_research")
        builder.add_edge("document_research", "graph_reasoning")
        builder.add_edge("graph_reasoning", "answer")
        builder.add_edge("answer", "evidence_check")
        builder.add_edge("evidence_check", "output_boundary")
        builder.add_edge("output_boundary", "finalize")
        builder.add_edge("finalize", END)
        return builder.compile(checkpointer=self._checkpointer)

    def close(self) -> None:
        self._connection.close()
