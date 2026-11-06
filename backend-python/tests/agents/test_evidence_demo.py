import runpy
from pathlib import Path

import httpx
import pytest


@pytest.mark.parametrize("scenario,mode,reason", [
    ("bm25", "bm25", None),
    ("rerank", "bm25_rerank", None),
    ("rerank_failed", "bm25", "RERANK_FAILED"),
    ("rerank_empty", "bm25", "RERANK_EMPTY"),
    ("no_evidence", "none", None),
])
def test_offline_demo_preserves_evidence_and_reports_actual_retrieval(monkeypatch, scenario, mode, reason):
    # A local credential must not switch this demo to a live provider.
    monkeypatch.setenv("DEEPSEEK_API_KEY", "unused-local-fixture-key")
    original_send = httpx.Client.send

    def offline_send(client, request, *args, **kwargs):
        assert isinstance(client._transport, httpx.MockTransport), "Demo attempted a live HTTP request"
        return original_send(client, request, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "send", offline_send)
    demo = runpy.run_path(str(Path(__file__).resolve().parents[3] / "scripts/demo/run-evidence-case.py"))
    case = demo["run_case"](scenario)
    result = case["result"]
    summary = result["retrieval"]
    assert summary["mode"] == case["retrievalEvent"]["mode"] == mode
    assert summary["degraded"] is (reason is not None)
    assert summary["degradationReasons"] == ([reason] if reason else [])
    assert "complete" in case["eventTypes"]
    assert result["workflow"][-1] == "COMPLETE"
    assert "无来源断言" not in result["answer"]
    if scenario == "no_evidence":
        assert result["citations"] == result["claims"] == []
        assert "证据不足" in result["answer"]
    else:
        expected_order = ["demo-b", "demo-a"] if scenario == "rerank" else ["demo-a", "demo-b"]
        assert [item["id"] for item in result["candidateEntities"]] == expected_order
        assert [item["id"] for item in result["citations"]] == ["doc:demo-a"]
        assert result["claims"][0]["evidenceIds"] == ["doc:demo-a"]
        assert "doc:demo-a" in result["answer"]
        assert result["graphRelations"][0]["relation"] == "HAS_SYMPTOM"
        assert result["warnings"] == ["已移除缺少直接证据支持的陈述"]
