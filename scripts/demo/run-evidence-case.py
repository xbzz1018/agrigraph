"""Run the real workflow with synthetic evidence and offline model/service fixtures."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend-python"))

from app.agents.chat_graph import MainAgentGraph  # noqa: E402
from app.agents.chat_service import AgentService  # noqa: E402
from app.agents.runtime import AgentRuntime  # noqa: E402
from app.agents.tools import ToolRegistry  # noqa: E402
from app.api.schemas import ChatRequest  # noqa: E402
from app.core.settings import Settings  # noqa: E402
from app.domain.models import AgricultureQuery, AnswerDraft  # noqa: E402
from app.integrations.model_gateway import ModelGateway  # noqa: E402
from app.integrations.semantic import RerankerGateway  # noqa: E402
from app.repositories import Repository  # noqa: E402

SCENARIOS = ("bm25", "rerank", "rerank_failed", "rerank_empty", "no_evidence")


class FixtureRetriever:
    def __init__(self, documents):
        self.documents = documents

    def search(self, query, crop_scope, limit):
        return [
            {"_id": item["id"], "_score": 0.9, "_source": copy.deepcopy(item),
             "_retrieval": {"mode": "bm25", "rank": rank, "degraded": False, "reason": ""}}
            for rank, item in enumerate(self.documents[:limit], 1)
        ]

    def raw_search(self, query, size):
        return []


class FixtureModel:
    evidence_payload = staticmethod(ModelGateway.evidence_payload)

    def structured(self, system, user, schema):
        if schema is AgricultureQuery:
            return AgricultureQuery(crop="番茄", taskType="SYMPTOM", symptoms=["褐色斑点"]), {}
        return AnswerDraft(answer="待核验的合成回答", claims=[
            {"text": "叶片可见褐色斑点", "evidenceIds": ["doc:demo-a"]},
            {"text": "无来源断言：已得到确定诊断", "evidenceIds": ["doc:missing"]},
        ]), {}


def run_case(scenario: str) -> dict:
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown demo scenario: {scenario}")
    fixture = json.loads((ROOT / "examples/evidence-case/fixture.json").read_text(encoding="utf-8"))
    # Ignore local environment variables and credentials; never load .env.ai or app.main.
    with patch.dict(os.environ, {}, clear=True):
        defaults = Settings.from_env()
    with TemporaryDirectory(prefix="agrigraph-demo-") as temporary:
        settings = replace(
            defaults, db_path=Path(temporary) / "demo.db", checkpoint_db_path=Path(temporary) / "checkpoint.db",
            reranker_api_base="https://reranker.invalid" if scenario.startswith("rerank") else "",
        )
        repository = Repository(settings.db_path)
        reranker = RerankerGateway(settings)
        reranker.close()

        def rerank_response(request):
            if scenario == "rerank_failed":
                return httpx.Response(503, json={"error": "synthetic upstream failure"})
            results = [] if scenario == "rerank_empty" else [
                {"index": 1, "relevance_score": 0.95}, {"index": 0, "relevance_score": 0.6}
            ]
            return httpx.Response(200, json={"results": results})

        if settings.reranker_api_base:
            reranker._client = httpx.Client(transport=httpx.MockTransport(rerank_response))
        documents = [] if scenario == "no_evidence" else fixture["documents"]
        relations = [] if scenario == "no_evidence" else fixture["graphRelations"]
        tools = ToolRegistry(
            settings, repository, retriever=FixtureRetriever(documents), reranker=reranker,
            graph_driver=SimpleNamespace(execute_query=lambda *args, **kwargs: SimpleNamespace(records=relations)),
        )
        graph = MainAgentGraph(AgentRuntime(settings, repository, tools, FixtureModel()), settings.checkpoint_db_path)
        try:
            events = list(AgentService(repository, graph).stream_run(
                "demo", "demo-thread", ChatRequest(question=fixture["question"], cropScope="TOMATO")
            ))
            payloads = dict(events)
            if "error" in payloads:
                raise RuntimeError(payloads["error"]["code"])
            result = payloads["complete"]
            keys = ("answer", "candidateEntities", "claims", "citations", "graphRelations", "warnings", "workflow", "retrieval")
            return {
                "scenario": scenario,
                "question": fixture["question"],
                "eventTypes": list(dict.fromkeys(event for event, _ in events)),
                "retrievalEvent": payloads["retrieval_result"],
                "result": {key: result[key] for key in keys},
            }
        finally:
            graph.close()
            reranker.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write an explicit JSON artifact; otherwise print JSON")
    args = parser.parse_args()
    sources = [
        "scripts/demo/run-evidence-case.py", "examples/evidence-case/fixture.json",
        "backend-python/app/agents/chat_graph.py", "backend-python/app/agents/chat_service.py",
        "backend-python/app/agents/runtime.py", "backend-python/app/agents/schemas.py",
        "backend-python/app/agents/tools.py", "backend-python/app/integrations/semantic.py",
    ]
    report = {
        "kind": "OFFLINE_SYNTHETIC_DEMO",
        "externalServices": "FixtureRetriever / FixtureModel / graph fixture / httpx.MockTransport",
        "sourceTextSha256": {
            name: hashlib.sha256((ROOT / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for name in sources
        },
        "scenarios": [run_case(scenario) for scenario in SCENARIOS],
    }
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"Wrote {len(report['scenarios'])} offline scenarios to {args.output}")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
