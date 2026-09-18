"""执行文本、图片和防治关系三组真实候选验收。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend-python"))

from app.evaluation.metrics import (  # noqa: E402
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

FIXTURES = ROOT / "tests" / "evaluation"
REPORTS = ROOT / "var" / "reports"
TEXT_CASES = REPORTS / "text-qa-cases.jsonl"
IMAGE_CASES = REPORTS / "image-understanding-cases.jsonl"
CONTROL_CASES = REPORTS / "control-relation-cases.jsonl"
SUMMARY = REPORTS / "multimodal-candidate-summary.json"


class EvaluationFailure(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise EvaluationFailure("MISSING_FIXTURE", f"缺少冻结评测集：{path.name}")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_manifest() -> str:
    suffixes = {".py", ".ps1", ".ts", ".vue", ".json", ".toml", ".yml", ".yaml", ".md"}
    excluded_parts = {"var", "logs", "dist", "node_modules", "__pycache__", ".ruff_cache"}
    excluded_names = {".env.ai", "task_plan.md", "findings.md", "progress.md"}
    scan_roots = [
        ROOT / "backend-python" / "app",
        ROOT / "backend-python" / "tests",
        ROOT / "backend-python" / "migrations",
        ROOT / "frontend" / "src",
        ROOT / "scripts",
        ROOT / "config",
        ROOT / "docs",
        ROOT / "tests",
    ]
    paths = [path for scan_root in scan_roots for path in scan_root.rglob("*")]
    paths.extend(
        path
        for path in (ROOT / "README.md", ROOT / "AGENTS.md", ROOT / "compose.yml", ROOT / ".env.ai.example")
        if path.is_file()
    )
    records = []
    for path in paths:
        if (
            not path.is_file()
            or path.suffix.lower() not in suffixes
            or path.name in excluded_names
            or excluded_parts.intersection(path.parts)
        ):
            continue
        records.append(f"{path.relative_to(ROOT).as_posix()}:{sha256(path)}")
    return hashlib.sha256("\n".join(sorted(records)).encode("utf-8")).hexdigest()


def api(client: httpx.Client, method: str, path: str, **kwargs: Any) -> Any:
    response = client.request(method, path, **kwargs)
    response.raise_for_status()
    payload = response.json()
    if int(payload.get("code", 0)) not in {0, 200}:
        raise EvaluationFailure("API_ERROR", str(payload.get("message") or path))
    return payload.get("data")


def validate_fixtures(
    text_rows: list[dict[str, Any]], image_rows: list[dict[str, Any]], control_rows: list[dict[str, Any]], data_root: Path
) -> None:
    if len(text_rows) != 160 or sum(bool(row.get("generationSelected")) for row in text_rows) != 40:
        raise EvaluationFailure("TEXT_FIXTURE_INVALID", "文本评测集必须为 160 条且生成子集为 40 条")
    if len(image_rows) != 30 or len({row["imageId"] for row in image_rows}) != 30:
        raise EvaluationFailure("IMAGE_FIXTURE_INVALID", "图片评测集必须为 30 张唯一图片")
    if sum(row["crop"] == "番茄" for row in image_rows) != 15 or sum(row["crop"] == "水稻" for row in image_rows) != 15:
        raise EvaluationFailure("IMAGE_STRATA_INVALID", "图片评测集番茄/水稻必须各 15 张")
    for row in image_rows:
        path = (data_root / row["sourceFile"]).resolve()
        if not path.is_relative_to(data_root) or not path.is_file() or sha256(path).lower() != row["sha256"].lower():
            raise EvaluationFailure("IMAGE_FILE_INVALID", f"图片缺失或哈希不符：{row['caseId']}")
    if len(control_rows) != 30 or len(
        {(row["diseaseId"], row["controlName"], row["controlType"]) for row in control_rows}
    ) != 30:
        raise EvaluationFailure("CONTROL_FIXTURE_INVALID", "防治关系评测集必须为 30 条唯一关系")
    if any(row.get("goldReviewMethod") != "SOURCE_CURATED_PUBLIC_DATA" for row in image_rows + control_rows):
        raise EvaluationFailure("GOLD_REVIEW_INVALID", "多模态金标审核口径不正确")


def text_evaluation(
    client: httpx.Client, rows: list[dict[str, Any]], timeout: int, workers: int
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    batch = api(
        client,
        "POST",
        "/evaluation/retrieve-batch",
        json={
            "queries": [
                {"id": row["id"], "question": row["question"], "crop": row.get("crop", "AUTO")} for row in rows
            ],
            "limit": 10,
        },
        timeout=timeout,
    )
    by_id = {str(item["id"]): list(item.get("bm25") or []) for item in batch}
    if set(by_id) != {str(row["id"]) for row in rows}:
        raise EvaluationFailure("TEXT_BATCH_INCOMPLETE", "BM25 批量结果与冻结样本不一致")
    retrieval = retrieval_metrics(rows, by_id)
    generation_rows = [row for row in rows if row.get("generationSelected")]

    def generate(row: dict[str, Any]) -> dict[str, Any]:
        try:
            answer = api(
                client,
                "POST",
                "/evaluation/answer",
                json={"question": row["question"], "crop": row.get("crop", "AUTO")},
                timeout=timeout,
            )
            score = score_text_answer(row, answer)
            model_ok = bool(answer.get("tokenUsage", {}).get("modelId"))
            degraded = any("暂不可用" in str(value) for value in answer.get("warnings", [])) or not model_ok
            return {
                "caseId": row["id"],
                "crop": row.get("crop"),
                "category": row.get("category"),
                "question": row["question"],
                "referenceAnswer": row.get("referenceAnswer", ""),
                "shouldAnswer": bool(row.get("shouldAnswer", True)),
                "actualAnswer": answer.get("answer", ""),
                "claims": answer.get("claims", []),
                "citations": answer.get("citations", []),
                "warnings": answer.get("warnings", []),
                "latencyMs": answer.get("latencyMs"),
                "tokenUsage": answer.get("tokenUsage", {}),
                "scoreDetails": score,
                "degraded": degraded,
            }
        except Exception as exc:  # noqa: BLE001 - 每条失败必须进入逐样例报告
            return {
                "caseId": row["id"],
                "crop": row.get("crop"),
                "category": row.get("category"),
                "question": row["question"],
                "referenceAnswer": row.get("referenceAnswer", ""),
                "shouldAnswer": bool(row.get("shouldAnswer", True)),
                "actualAnswer": "",
                "claims": [],
                "citations": [],
                "warnings": [],
                "latencyMs": None,
                "tokenUsage": {},
                "scoreDetails": {
                    "claimCoverage": 0.0,
                    "citationCoverage": 0.0,
                    "citationCorrectness": 0.0,
                    "refused": False,
                    "failureType": type(exc).__name__,
                },
                "degraded": True,
            }

    with ThreadPoolExecutor(max_workers=min(workers, len(generation_rows))) as executor:
        generation = list(executor.map(generate, generation_rows))
    cases = [
        {
            "caseId": row["id"],
            "question": row["question"],
            "expectedEntityIds": row.get("expectedEntityIds", []),
            "retrievalResults": by_id[row["id"]],
            "generation": next((item for item in generation if item["caseId"] == row["id"]), None),
        }
        for row in rows
    ]
    return cases, {"retrieval": retrieval, "generation": aggregate_text_metrics(generation)}, generation


def image_evaluation(
    base_url: str,
    token: str,
    rows: list[dict[str, Any]],
    data_root: Path,
    timeout: int,
    workers: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    def evaluate(row: dict[str, Any]) -> dict[str, Any]:
        path = data_root / row["sourceFile"]
        try:
            with path.open("rb") as stream:
                response = httpx.post(
                    f"{base_url}/diagnosis/image",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"crop": row["crop"]},
                    files={"image": (path.name, stream, "image/webp")},
                    timeout=timeout,
                )
            response.raise_for_status()
            result = response.json().get("data") or {}
            score = score_image_case(row, result)
            model_ok = bool(result.get("tokenUsage", {}).get("modelId"))
            degraded = any("暂不可用" in str(value) for value in result.get("warnings", [])) or not model_ok
            return {
                "caseId": row["caseId"],
                "imageId": row["imageId"],
                "crop": row["crop"],
                "entityId": row["entityId"],
                "entityName": row["entityName"],
                "expectedSymptoms": row["expectedSymptoms"],
                "observation": result.get("observation"),
                "candidateEntities": result.get("candidateEntities", []),
                "claims": result.get("claims", []),
                "citations": result.get("citations", []),
                "warnings": result.get("warnings", []),
                "latencyMs": result.get("latencyMs"),
                "tokenUsage": result.get("tokenUsage", {}),
                "scoreDetails": score,
                "degraded": degraded,
            }
        except Exception as exc:  # noqa: BLE001 - 每张图片失败都必须保留
            return {
                "caseId": row["caseId"],
                "imageId": row["imageId"],
                "crop": row["crop"],
                "entityId": row["entityId"],
                "entityName": row["entityName"],
                "expectedSymptoms": row["expectedSymptoms"],
                "observation": None,
                "candidateEntities": [],
                "claims": [],
                "citations": [],
                "warnings": [],
                "latencyMs": None,
                "tokenUsage": {},
                "scoreDetails": {
                    "schemaSuccess": False,
                    "symptomCoverage": 0.0,
                    "candidateRecalledAt3": False,
                    "failureType": type(exc).__name__,
                },
                "degraded": True,
            }

    with ThreadPoolExecutor(max_workers=min(workers, len(rows))) as executor:
        results = list(executor.map(evaluate, rows))
    return results, aggregate_image_metrics(results)


def control_evaluation(
    client: httpx.Client, rows: list[dict[str, Any]], timeout: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    disease_ids = list(dict.fromkeys(str(row["diseaseId"]) for row in rows))
    response = api(
        client,
        "POST",
        "/evaluation/control-relations-batch",
        json={"diseaseIds": disease_ids},
        timeout=timeout,
    )
    by_id = {str(item["diseaseId"]): item for item in response}
    results = []
    for row in rows:
        actual = by_id.get(str(row["diseaseId"]), {"controlOptions": [], "graphRelations": []})
        results.append(
            {
                "caseId": row["caseId"],
                "crop": row["crop"],
                "diseaseId": row["diseaseId"],
                "diseaseName": row["diseaseName"],
                "controlName": row["controlName"],
                "controlType": row["controlType"],
                "controlOptions": actual.get("controlOptions", []),
                "graphRelations": actual.get("graphRelations", []),
                "scoreDetails": score_control_case(row, actual),
            }
        )
    return results, aggregate_control_metrics(results)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8188/api/v1")
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--request-timeout", type=int, default=900)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--preflight-report", default=str(REPORTS / "model-preflight.json"))
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--refresh-text", action="store_true")
    parser.add_argument("--refresh-image", action="store_true")
    parser.add_argument("--refresh-control", action="store_true")
    args = parser.parse_args()
    REPORTS.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    base_url = args.base.rstrip("/")
    with httpx.Client(base_url=base_url, timeout=args.request_timeout) as client:
        infrastructure = api(client, "GET", "/health/dependencies", timeout=30)
        if args.preflight:
            print(json.dumps({"status": infrastructure.get("status"), "dependencies": infrastructure.get("dependencies")}, ensure_ascii=False))
            return 0 if infrastructure.get("status") == "UP" else 1
        text_path = FIXTURES / "agriculture-rag-test-v2.jsonl"
        image_path = FIXTURES / "multimodal-image-test.jsonl"
        control_path = FIXTURES / "control-relation-test.jsonl"
        text_rows = load_jsonl(text_path)
        image_rows = load_jsonl(image_path)
        control_rows = load_jsonl(control_path)
        data_root = Path(args.data_root).resolve()
        validate_fixtures(text_rows, image_rows, control_rows, data_root)
        preflight_path = Path(args.preflight_report).resolve()
        preflight = json.loads(preflight_path.read_text(encoding="utf-8")) if preflight_path.is_file() else {}
        token = ""
        if not args.resume or args.refresh_text or args.refresh_image or args.refresh_control:
            username = os.getenv("AGRIGRAPH_EVAL_USERNAME", "agrigraph_acceptance")
            password = os.getenv("AGRIGRAPH_EVAL_PASSWORD", "")
            token = str(
                api(client, "POST", "/users/login", json={"username": username, "password": password})["token"]
            )
            client.headers["Authorization"] = f"Bearer {token}"
        if args.resume:
            if not all(path.is_file() for path in (TEXT_CASES, IMAGE_CASES, CONTROL_CASES)):
                raise EvaluationFailure("RESUME_REPORT_MISSING", "恢复汇总所需的逐样例报告不完整")
            text_cases = load_jsonl(TEXT_CASES)
            image_cases = load_jsonl(IMAGE_CASES)
            control_cases = load_jsonl(CONTROL_CASES)
            retrieval_by_id = {
                str(item["caseId"]): list(item.get("retrievalResults") or []) for item in text_cases
            }
            text_runs = [item["generation"] for item in text_cases if item.get("generation")]
            text_metrics = {
                "retrieval": retrieval_metrics(text_rows, retrieval_by_id),
                "generation": aggregate_text_metrics(text_runs),
            }
            image_metrics = aggregate_image_metrics(image_cases)
            control_metrics = aggregate_control_metrics(control_cases)
            if args.refresh_text:
                text_cases, text_metrics, text_runs = text_evaluation(
                    client, text_rows, args.request_timeout, args.workers
                )
                write_jsonl(TEXT_CASES, text_cases)
            if args.refresh_image:
                image_cases, image_metrics = image_evaluation(
                    base_url, token, image_rows, data_root, args.request_timeout, min(2, args.workers)
                )
                write_jsonl(IMAGE_CASES, image_cases)
            if args.refresh_control:
                control_cases, control_metrics = control_evaluation(client, control_rows, args.request_timeout)
                write_jsonl(CONTROL_CASES, control_cases)
        else:
            text_cases, text_metrics, text_runs = text_evaluation(
                client, text_rows, args.request_timeout, args.workers
            )
            write_jsonl(TEXT_CASES, text_cases)
            image_cases, image_metrics = image_evaluation(
                base_url, token, image_rows, data_root, args.request_timeout, min(2, args.workers)
            )
            write_jsonl(IMAGE_CASES, image_cases)
            control_cases, control_metrics = control_evaluation(client, control_rows, args.request_timeout)
            write_jsonl(CONTROL_CASES, control_cases)
    checks, failures = candidate_gates(
        text_metrics, text_runs, image_metrics, image_cases, control_metrics, infrastructure, preflight
    )
    status = "COMPLETED_CANDIDATE" if not failures else "FAILED_CANDIDATE"
    summary = {
        "kind": "agrigraph-multimodal-candidate",
        "status": status,
        "releaseClass": "CANDIDATE_NOT_FORMAL_RELEASE",
        "sourceState": "UNVERSIONED_LOCAL",
        "sourceManifestSha256": source_manifest(),
        "datasetSha256": {
            "text": sha256(text_path),
            "image": sha256(image_path),
            "control": sha256(control_path),
        },
        "modelId": preflight.get("deepseek", {}).get("modelId"),
        "visionModelId": preflight.get("vision", {}).get("modelId"),
        "promptSha256": sha256(ROOT / "backend-python" / "app" / "agents" / "runtime.py"),
        "workflowSha256": sha256(ROOT / "backend-python" / "app" / "agents" / "chat_graph.py"),
        "toolSchemaSha256": sha256(ROOT / "backend-python" / "app" / "agents" / "tools.py"),
        "infrastructure": infrastructure,
        "modelPreflight": preflight,
        "metrics": {"text": text_metrics, "image": image_metrics, "control": control_metrics},
        "engineeringDiagnostics": engineering_diagnostics([*text_runs, *image_cases]),
        "gates": checks,
        "failureTypes": failures,
        "counts": {"text": len(text_rows), "generation": len(text_runs), "image": len(image_cases), "control": len(control_cases)},
        "evaluationRunId": str(uuid.uuid4()),
        "elapsedSeconds": round(time.perf_counter() - started, 2),
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": status, "failureTypes": failures, "summary": str(SUMMARY)}, ensure_ascii=False))
    return 0 if status == "COMPLETED_CANDIDATE" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except EvaluationFailure as exc:
        REPORTS.mkdir(parents=True, exist_ok=True)
        failure = {"status": "FAILED_CANDIDATE", "failureTypes": [exc.code], "message": str(exc)}
        SUMMARY.write_text(json.dumps(failure, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(failure, ensure_ascii=False))
        raise SystemExit(1) from exc
