"""三组公开指标必须保持确定性和可独立复核。"""

from app.evaluation.metrics import (
    aggregate_control_metrics,
    aggregate_image_metrics,
    aggregate_text_metrics,
    candidate_gates,
    engineering_diagnostics,
    retrieval_metrics,
    score_control_case,
    score_image_case,
    score_text_answer,
)


def test_retrieval_metrics_ignore_negative_samples() -> None:
    rows = [{"id": "p", "expectedEntityIds": ["e1"]}, {"id": "n", "expectedEntityIds": []}]
    metrics = retrieval_metrics(rows, {"p": [{"fileMd5": "e1"}], "n": []})
    assert metrics == {"Recall@10": 1.0, "MRR": 1.0, "nDCG@10": 1.0, "samples": 1}


def test_text_claim_and_citation_metrics_use_gold_ids() -> None:
    row = {
        "shouldAnswer": True,
        "expectedClaims": [
            {"claimId": "c1", "requiredTerms": ["高湿"], "supportingEvidenceIds": ["e1"]},
            {"claimId": "c2", "requiredTerms": ["病斑"], "supportingEvidenceIds": ["e1"]},
        ],
    }
    score = score_text_answer(
        row,
        {"answer": "高湿条件下容易发生。", "citations": [{"id": "doc:e1"}, {"id": "doc:other"}]},
    )
    assert score["claimCoverage"] == 0.5
    assert score["citationCoverage"] == 1.0
    assert score["citationCorrectness"] == 0.5
    assert score["failureType"] == "CLAIM_MISS"


def test_text_aggregate_keeps_negative_refusal_separate() -> None:
    positive = {
        "shouldAnswer": True,
        "scoreDetails": {"claimCoverage": 1.0, "citationCoverage": 1.0, "citationCorrectness": 1.0, "refused": False},
    }
    negative = {
        "shouldAnswer": False,
        "scoreDetails": {"claimCoverage": 0.0, "citationCoverage": 0.0, "citationCorrectness": 0.0, "refused": True},
    }
    metrics = aggregate_text_metrics([positive, negative])
    assert metrics["ClaimCoverage"] == 1.0
    assert metrics["NegativeRefusalRate"] == 1.0


def test_image_metrics_validate_schema_symptoms_and_candidate() -> None:
    row = {"expectedSymptoms": ["黄化", "病斑"], "entityId": "e1"}
    result = {
        "observation": {"crop": "水稻", "plantParts": ["叶片"], "symptoms": ["叶片黄化并有病斑"], "qualityWarnings": []},
        "candidateEntities": [{"id": "e2"}, {"id": "e1"}],
    }
    score = score_image_case(row, result)
    metrics = aggregate_image_metrics([{"scoreDetails": score}])
    assert metrics["SchemaSuccessRate"] == 1.0
    assert metrics["SymptomCoverage"] == 1.0
    assert metrics["CandidateRecall@3"] == 1.0


def test_control_metrics_require_graph_relation_and_reject_usage_leak() -> None:
    row = {"controlName": "三环唑", "controlType": "ACTIVE_INGREDIENT", "diseaseId": "d1"}
    result = {
        "controlOptions": [
            {"name": "三环唑", "type": "ACTIVE_INGREDIENT", "targetDiseaseId": "d1", "evidenceIds": ["doc:d1"]}
        ],
        "graphRelations": [
            {"source": "三环唑", "relation": "CONTROLS", "targetId": "d1", "target": "稻瘟病"}
        ],
    }
    score = score_control_case(row, result)
    metrics = aggregate_control_metrics([{"scoreDetails": score}])
    assert metrics["Recall@5"] == 1.0
    assert metrics["RelationCorrectness"] == 1.0
    assert metrics["UsageLeakRate"] == 0.0
    leaked = score_control_case(row, {**result, "answer": "每亩用100克兑水喷雾"})
    assert leaked["usageLeak"] is True


def test_engineering_diagnostics_keep_unknown_cost_null() -> None:
    diagnostics = engineering_diagnostics(
        [{"latencyMs": 100, "tokenUsage": {"totalTokens": 20, "estimatedCostUsd": None}}]
    )
    assert diagnostics["averageCostUsd"] is None
    assert diagnostics["pricingConfigured"] is False


def test_candidate_gate_rejects_incomplete_or_degraded_runs() -> None:
    text = {
        "retrieval": {"Recall@10": 0.9},
        "generation": {"ClaimCoverage": 0.8, "CitationCoverage": 0.8, "CitationCorrectness": 0.8},
    }
    image = {"SchemaSuccessRate": 1.0, "CandidateRecall@3": 0.8}
    control = {"RelationCorrectness": 1.0, "UsageLeakRate": 0.0}
    checks, failures = candidate_gates(
        text,
        [{"degraded": False}] * 39,
        image,
        [{"degraded": False}] * 30,
        control,
        {"status": "UP"},
        {"status": "PASSED"},
    )
    assert checks["textComplete"] is False
    assert failures == ["textComplete"]
