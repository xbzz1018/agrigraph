from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.agents.chat_service import AgentService
from app.agents.schemas import summarize_retrieval
from app.api.schemas import ChatRequest
from app.integrations.semantic import RerankerGateway
from app.main import create_app


@pytest.mark.parametrize("mode,degraded,reason", [
    ("bm25", False, ""),
    ("bm25_rerank", False, ""),
    ("bm25", True, "RERANK_FAILED"),
    ("bm25", True, "RERANK_EMPTY"),
])
def test_sse_and_final_result_use_actual_retrieval(settings, repository, mode, degraded, reason):
    document = {"id": "doc:1", "title": "fixture", "excerpt": "public fixture", "score": 0.9,
                "metadata": {"retrieval": {"mode": mode, "degraded": degraded, "reason": reason}}}

    def stream(initial, **kwargs):
        yield {**initial, "document_evidence": [document], "final_answer": "fixture", "citation_ids": ["doc:1"]}

    graph = SimpleNamespace(graph=SimpleNamespace(stream=stream), runtime=SimpleNamespace(settings=settings))
    service = AgentService(repository, graph)
    events = dict(service.stream_run("tester", "test-thread", ChatRequest(question="fixture")))
    assert "error" not in events
    summary = events["complete"]["retrieval"]
    assert events["retrieval_result"]["mode"] == summary["mode"] == mode
    assert events["complete"]["retrievalMode"] == mode
    assert summary["degraded"] is degraded
    assert summary["degradationReasons"] == ([reason] if reason else [])


def test_no_evidence_is_none_and_arbitrary_provider_error_is_not_exposed():
    assert summarize_retrieval([]).mode == "none"
    result = summarize_retrieval([{"metadata": {"retrieval": {
        "mode": "bm25", "degraded": True, "reason": "secret provider response"
    }}}])
    assert result.degradationReasons == ["RETRIEVAL_DEGRADED"]
    assert "secret" not in result.model_dump_json()


@pytest.mark.parametrize("failure", ["http", "empty"])
def test_real_gateway_boundary_returns_auditable_fallback(settings, failure):
    gateway = RerankerGateway(replace(settings, reranker_api_base="https://fake.invalid"))
    gateway.close()

    def handler(request):
        if failure == "http":
            return httpx.Response(503, json={"error": "do not expose"})
        return httpx.Response(200, json={"results": []})

    gateway._client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        hits = [{"_id": "one", "_source": {"name": "fixture"}, "_retrieval": {"mode": "bm25", "rank": 1}}]
        result = gateway.rerank("fixture", hits, 1)
        assert result[0]["_id"] == "one"
        assert result[0]["_retrieval"]["degraded"] is True
        assert result[0]["_retrieval"]["reason"] == ("RERANK_FAILED" if failure == "http" else "RERANK_EMPTY")
    finally:
        gateway.close()


def test_gateway_disabled_and_successful_rerank(settings):
    hits = [{"_id": "one", "_source": {"name": "fixture"}, "_retrieval": {"mode": "bm25", "rank": 1}}]
    disabled = RerankerGateway(replace(settings, reranker_api_base=""))
    assert disabled.rerank("fixture", hits, 1) == hits
    gateway = RerankerGateway(replace(settings, reranker_api_base="https://fake.invalid"))
    gateway.close()
    gateway._client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"results": [{"index": 0, "relevance_score": 0.8}]})
    ))
    try:
        result = gateway.rerank("fixture", hits, 1)
        assert result[0]["_retrieval"]["mode"] == "bm25_rerank"
        assert result[0]["_retrieval"]["degraded"] is False
    finally:
        gateway.close()


@pytest.mark.parametrize("enabled", [False, True])
def test_health_is_configured_policy_and_openapi_includes_actual_modes(settings, enabled):
    configured = replace(settings, reranker_api_base="https://fake.invalid" if enabled else "")
    with TestClient(create_app(configured)) as client:
        health = client.get("/api/v1/health").json()["data"]
        assert health["rerankerConfigured"] is enabled
        assert health["retrievalModeKind"] == "configured_policy"
        assert health["retrievalMode"] == ("bm25_conditional_rerank" if enabled else "bm25")
        schema = client.get("/openapi.json").json()["components"]["schemas"]["RetrievalSummary"]
        assert schema["properties"]["mode"]["enum"] == ["none", "bm25", "bm25_rerank"]
