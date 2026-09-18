"""三组多模态知识服务评测指标，均可脱离模型独立复核。"""

from __future__ import annotations

import math
import re
import unicodedata
from statistics import mean
from typing import Any

from app.domain.control import contains_restricted_usage

REFUSAL_TERMS = (
    "当前知识库没有找到",
    "当前证据不足",
    "无法回答",
    "无法确定",
    "请补充",
    "登记标签",
)


def normalize_text(value: Any) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).lower()
    return "".join(character for character in normalized if character.isalnum())


def normalize_evidence_id(value: Any) -> str:
    result = str(value or "")
    return result[4:] if result.startswith("doc:") else result


def retrieval_metrics(rows: list[dict[str, Any]], results: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    recall10 = reciprocal = ndcg10 = eligible = 0.0
    for row in rows:
        relevant = {str(value) for value in row.get("expectedEntityIds", []) if value}
        if not relevant:
            continue
        eligible += 1
        ids = [str(item.get("fileMd5") or item.get("chunkId") or "") for item in results.get(row["id"], [])]
        ranks = sorted(ids.index(value) + 1 for value in relevant if value in ids)
        if not ranks:
            continue
        recall10 += int(ranks[0] <= 10)
        reciprocal += 1 / ranks[0]
        dcg = sum(1 / math.log2(rank + 1) for rank in ranks if rank <= 10)
        ideal = sum(1 / math.log2(index + 2) for index in range(min(len(relevant), 10)))
        ndcg10 += dcg / ideal if ideal else 0
    divisor = max(eligible, 1)
    return {
        "Recall@10": round(recall10 / divisor, 4),
        "MRR": round(reciprocal / divisor, 4),
        "nDCG@10": round(ndcg10 / divisor, 4),
        "samples": int(eligible),
    }


def _term_matches(answer: str, term: Any) -> bool:
    actual = normalize_text(answer)
    raw = unicodedata.normalize("NFKC", str(term or ""))
    variants = [raw, re.sub(r"^\s*[（(]?\d+[)）.、]?\s*", "", raw)]
    for value in variants:
        expected = normalize_text(value)
        if not expected:
            continue
        if expected in actual:
            return True
        if len(expected) < 8:
            continue
        pairs = {expected[index : index + 2] for index in range(len(expected) - 1)}
        if sum(pair in actual for pair in pairs) / max(len(pairs), 1) >= 0.65:
            return True
    return False


def score_text_answer(row: dict[str, Any], answer: dict[str, Any]) -> dict[str, Any]:
    text = str(answer.get("answer", ""))
    citation_ids = {
        normalize_evidence_id(item.get("id")) for item in answer.get("citations", []) if item.get("id")
    }
    details: list[dict[str, Any]] = []
    supported_citations: set[str] = set()
    for claim in row.get("expectedClaims", []):
        terms = [term for term in claim.get("requiredTerms", []) if term]
        matched = bool(terms) and all(_term_matches(text, term) for term in terms)
        gold_ids = {
            normalize_evidence_id(value)
            for value in claim.get("supportingEvidenceIds", row.get("supportingEvidenceIds", []))
        }
        supporting = citation_ids & gold_ids if matched else set()
        supported_citations.update(supporting)
        details.append(
            {
                "claimId": claim.get("claimId"),
                "matched": matched,
                "citationSupported": bool(supporting),
                "supportingCitationIds": sorted(supporting),
            }
        )
    matched = sum(item["matched"] for item in details)
    supported = sum(item["citationSupported"] for item in details)
    claims = len(details)
    refusal = any(term in text for term in REFUSAL_TERMS)
    should_answer = bool(row.get("shouldAnswer", True))
    failure = None
    if should_answer and refusal:
        failure = "FALSE_REFUSAL"
    elif should_answer and matched < claims:
        failure = "CLAIM_MISS"
    elif should_answer and supported < matched:
        failure = "CITATION_GAP"
    elif not should_answer and not refusal:
        failure = "NEGATIVE_NOT_REFUSED"
    return {
        "claimDetails": details,
        "claimCoverage": round(matched / max(claims, 1), 4),
        "citationCoverage": round(supported / max(matched, 1), 4),
        "citationCorrectness": round(len(supported_citations) / max(len(citation_ids), 1), 4),
        "refused": refusal,
        "failureType": failure,
    }


def aggregate_text_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    positives = [item for item in results if item["shouldAnswer"]]
    negatives = [item for item in results if not item["shouldAnswer"]]
    return {
        "ClaimCoverage": round(mean(item["scoreDetails"]["claimCoverage"] for item in positives), 4),
        "CitationCoverage": round(mean(item["scoreDetails"]["citationCoverage"] for item in positives), 4),
        "CitationCorrectness": round(
            mean(item["scoreDetails"]["citationCorrectness"] for item in positives), 4
        ),
        "NegativeRefusalRate": round(
            sum(item["scoreDetails"]["refused"] for item in negatives) / max(len(negatives), 1), 4
        ),
        "positiveSamples": len(positives),
        "negativeSamples": len(negatives),
    }


def score_image_case(row: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    observation = result.get("observation") or {}
    schema_success = (
        observation.get("crop") in {"番茄", "水稻", "未知"}
        and isinstance(observation.get("plantParts"), list)
        and isinstance(observation.get("symptoms"), list)
        and isinstance(observation.get("qualityWarnings"), list)
    )
    actual_symptoms = " ".join(str(value) for value in observation.get("symptoms", []))
    expected = [str(value) for value in row.get("expectedSymptoms", []) if value]
    symptom_coverage = sum(_term_matches(actual_symptoms, term) for term in expected) / max(len(expected), 1)
    candidates = [str(item.get("id", "")) for item in result.get("candidateEntities", [])[:3]]
    recalled = str(row.get("entityId", "")) in candidates
    return {
        "schemaSuccess": bool(schema_success),
        "symptomCoverage": round(symptom_coverage, 4),
        "candidateRecalledAt3": recalled,
        "failureType": None if schema_success and recalled else ("VISION_SCHEMA" if not schema_success else "CANDIDATE_MISS"),
    }


def aggregate_image_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    divisor = max(len(results), 1)
    return {
        "SchemaSuccessRate": round(sum(item["scoreDetails"]["schemaSuccess"] for item in results) / divisor, 4),
        "SymptomCoverage": round(mean(item["scoreDetails"]["symptomCoverage"] for item in results), 4),
        "CandidateRecall@3": round(
            sum(item["scoreDetails"]["candidateRecalledAt3"] for item in results) / divisor, 4
        ),
        "samples": len(results),
    }


def score_control_case(row: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    expected_name = normalize_text(row.get("controlName"))
    expected_type = str(row.get("controlType", ""))
    disease_id = str(row.get("diseaseId", ""))
    options = [
        item for item in result.get("controlOptions", []) if item.get("type") == expected_type
    ][:5]
    relations = list(result.get("graphRelations") or [])
    match = next(
        (
            item
            for item in options
            if normalize_text(item.get("name")) == expected_name
            and item.get("type") == expected_type
            and str(item.get("targetDiseaseId", "")) == disease_id
        ),
        None,
    )
    expected_relation = "PREVENTS" if expected_type == "AGRICULTURAL" else "CONTROLS"
    graph_match = any(
        item.get("relation") == expected_relation
        and normalize_text(item.get("source")) == expected_name
        and str(item.get("targetId", "")) == disease_id
        for item in relations
    )
    valid_options = [
        item
        for item in options
        if item.get("type") in {"AGRICULTURAL", "BIOLOGICAL", "ACTIVE_INGREDIENT"}
        and str(item.get("targetDiseaseId", "")) == disease_id
        and item.get("evidenceIds")
    ]
    exposed = contains_restricted_usage(json_safe_text(result))
    return {
        "recalledAt5": bool(match),
        "relationCorrect": bool(match and graph_match and len(valid_options) == len(options)),
        "usageLeak": exposed,
        "failureType": None if match and graph_match and not exposed else (
            "USAGE_LEAK" if exposed else "CONTROL_RELATION_MISS"
        ),
    }


def aggregate_control_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    divisor = max(len(results), 1)
    return {
        "Recall@5": round(sum(item["scoreDetails"]["recalledAt5"] for item in results) / divisor, 4),
        "RelationCorrectness": round(
            sum(item["scoreDetails"]["relationCorrect"] for item in results) / divisor, 4
        ),
        "UsageLeakRate": round(sum(item["scoreDetails"]["usageLeak"] for item in results) / divisor, 4),
        "samples": len(results),
    }


def json_safe_text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(json_safe_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(json_safe_text(item) for item in value)
    return str(value or "")


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower, upper = math.floor(position), math.ceil(position)
    value = ordered[lower] if lower == upper else ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
    return round(value, 2)


def engineering_diagnostics(results: list[dict[str, Any]]) -> dict[str, Any]:
    latencies = [float(item["latencyMs"]) for item in results if item.get("latencyMs") is not None]
    tokens = [
        float(item["tokenUsage"]["totalTokens"])
        for item in results
        if item.get("tokenUsage", {}).get("totalTokens") is not None
    ]
    costs = [
        float(item["tokenUsage"]["estimatedCostUsd"])
        for item in results
        if item.get("tokenUsage", {}).get("estimatedCostUsd") is not None
    ]
    return {
        "latencyMs": {"p50": percentile(latencies, 0.5), "p95": percentile(latencies, 0.95)},
        "averageTokens": round(mean(tokens), 2) if tokens else None,
        "averageCostUsd": round(mean(costs), 8) if costs and len(costs) == len(results) else None,
        "pricingConfigured": bool(results) and len(costs) == len(results),
    }


def candidate_gates(
    text: dict[str, Any],
    text_runs: list[dict[str, Any]],
    image: dict[str, Any],
    image_runs: list[dict[str, Any]],
    control: dict[str, Any],
    infrastructure: dict[str, Any],
    preflight: dict[str, Any],
) -> tuple[dict[str, bool], list[str]]:
    checks = {
        "infrastructure": infrastructure.get("status") == "UP",
        "modelPreflight": preflight.get("status") == "PASSED",
        "textRecall10": text["retrieval"]["Recall@10"] >= 0.8681,
        "claimCoverage": text["generation"]["ClaimCoverage"] >= 0.75,
        "citationCoverage": text["generation"]["CitationCoverage"] >= 0.75,
        "citationCorrectness": text["generation"]["CitationCorrectness"] >= 0.70,
        "textComplete": len(text_runs) == 40 and not any(item["degraded"] for item in text_runs),
        "visionSchema": image["SchemaSuccessRate"] >= 0.95,
        "imageRecall3": image["CandidateRecall@3"] >= 0.70,
        "imageComplete": len(image_runs) == 30 and not any(item["degraded"] for item in image_runs),
        "controlCorrectness": control["RelationCorrectness"] >= 0.90,
        "controlUsageLeak": control["UsageLeakRate"] == 0,
    }
    return checks, [name for name, passed in checks.items() if not passed]
