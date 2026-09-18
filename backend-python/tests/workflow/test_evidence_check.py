from app.agents.runtime import AgentRuntime


def test_evidence_check_rebuilds_answer_from_supported_claims() -> None:
    runtime = AgentRuntime(None, None, None, None)  # type: ignore[arg-type]
    state = {
        "run_id": "r1",
        "draft_answer": "高湿容易发病。不存在的剂量建议。",
        "draft_claims": [
            {"text": "高湿容易发病", "evidenceIds": ["doc:e1"]},
            {"text": "每亩使用100克", "evidenceIds": ["doc:e1"]},
        ],
        "document_evidence": [{"id": "doc:e1", "excerpt": "高湿容易发病，叶片出现病斑。"}],
        "graph_evidence": [],
    }
    result = runtime.evidence_check(state)  # type: ignore[arg-type]
    assert result["citation_ids"] == ["doc:e1"]
    assert "高湿容易发病" in result["draft_answer"]
    assert "100克" not in result["draft_answer"]
    assert len(result["draft_claims"]) == 1
