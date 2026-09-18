"""从只读公开数据生成图片与防治关系冻结评测集。"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend-python"))

from app.domain.control import extract_control_options  # noqa: E402

OUTPUT = ROOT / "tests" / "evaluation"
REVIEW_METHOD = "SOURCE_CURATED_PUBLIC_DATA"
VISUAL_TERMS = {
    "孔洞": ["孔洞", "穿孔"],
    "缺刻": ["缺刻"],
    "虫道": ["虫道", "潜痕", "食痕"],
    "蛀孔": ["蛀孔", "蛀食", "蛀入"],
    "枯鞘": ["枯鞘"],
    "死穗": ["死穗", "死孕穗"],
    "虫体可见": ["幼虫", "成虫", "虫卵"],
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def round_robin(rows: list[dict[str, Any]], count: int, key: str) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in sorted(rows, key=lambda value: (str(value.get(key, "")), str(value.get("sha256", "")))):
        buckets[str(row.get(key, ""))].append(row)
    selected: list[dict[str, Any]] = []
    names = sorted(buckets)
    while len(selected) < count and any(buckets.values()):
        for name in names:
            if buckets[name] and len(selected) < count:
                selected.append(buckets[name].pop(0))
    if len(selected) != count:
        raise ValueError(f"冻结样本不足：需要 {count}，实际 {len(selected)}")
    return selected


def ontology_terms(text: str, groups: dict[str, list[str]]) -> list[str]:
    return [name for name, aliases in groups.items() if any(alias in text for alias in aliases)]


def build_images(data_root: Path, entities: list[dict[str, Any]], ontology: dict[str, Any]) -> list[dict[str, Any]]:
    by_id = {str(item["id"]): item for item in entities}
    manifest = read_jsonl(data_root / "processed" / "knowledge" / "image-entity-map.jsonl")
    supplemental_path = data_root / "processed" / "knowledge" / "supplemental-images.jsonl"
    supplemental = {str(item["id"]): item for item in read_jsonl(supplemental_path)} if supplemental_path.is_file() else {}
    candidates: list[dict[str, Any]] = []
    for image in manifest:
        entity = by_id.get(str(image.get("entityId", "")))
        if entity is None or image.get("verificationStatus") != "VERIFIED":
            continue
        crop = str(image.get("crop") or entity.get("crop") or "")
        usage = str(image.get("usage") or "")
        relative = str(image.get("thumbnailFile") or image.get("sourceFile") or "")
        symptom_text = " ".join(
            str(entity.get(key, "")) for key in ("symptoms", "habits", "morphology") if entity.get(key)
        )
        expected_symptoms = list(
            dict.fromkeys(
                [
                    *ontology_terms(symptom_text, ontology["symptoms"]),
                    *ontology_terms(symptom_text, VISUAL_TERMS),
                ]
            )
        )
        if usage == "PEST_CASE" and "虫体可见" not in expected_symptoms:
            expected_symptoms.append("虫体可见")
        if usage == "DISEASE_CASE" and not expected_symptoms:
            expected_symptoms.append("病斑")
        expected_parts = ontology_terms(symptom_text, ontology["plantParts"])
        if (
            crop not in {"番茄", "水稻"}
            or usage not in {"DISEASE_CASE", "PEST_CASE"}
            or not relative
            or not (data_root / relative).is_file()
            or not expected_symptoms
        ):
            continue
        candidates.append(
            {
                "imageId": str(image["id"]),
                "sha256": hashlib.sha256((data_root / relative).read_bytes()).hexdigest(),
                "sourceFile": relative.replace("\\", "/"),
                "sourcePage": str(image.get("sourcePage") or ""),
                "license": str(image.get("license") or ""),
                "licenseUrl": str(image.get("licenseUrl") or ""),
                "crop": crop,
                "usage": usage,
                "entityId": str(entity["id"]),
                "entityName": str(entity.get("name") or image.get("entityName") or ""),
                "entityType": str(entity.get("entityTypeCode") or image.get("entityType") or ""),
                "expectedPlantParts": expected_parts,
                "expectedSymptoms": expected_symptoms,
                "sourceTitle": str(supplemental.get(str(image["id"]), {}).get("title") or ""),
            }
        )
    quotas = {
        ("番茄", "DISEASE_CASE"): 8,
        ("番茄", "PEST_CASE"): 7,
        ("水稻", "DISEASE_CASE"): 7,
        ("水稻", "PEST_CASE"): 8,
    }
    selected: list[dict[str, Any]] = []
    for (crop, usage), count in quotas.items():
        values = [row for row in candidates if row["crop"] == crop and row["usage"] == usage]
        # 优先保留能看到作物/受害部位的图片；单一实体允许多张图，避免把昆虫标本当作田间症状样本。
        values.sort(
            key=lambda row: (
                not any(term in row["sourceTitle"].lower() for term in ("plant", "leaf", "rice", "tomato", "affected", "under")),
                row["entityId"],
                row["sha256"],
            )
        )
        if len(values) < count:
            raise ValueError(f"冻结样本不足：{crop}/{usage} 需要 {count}，实际 {len(values)}")
        selected.extend(values[:count])
    selected.sort(key=lambda row: (row["crop"], row["usage"], row["entityId"], row["sha256"]))
    return [
        {
            "caseId": f"IMG-{index:03d}",
            **row,
            "goldReviewed": True,
            "goldReviewMethod": REVIEW_METHOD,
        }
        for index, row in enumerate(selected, 1)
    ]


def build_controls(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for entity in entities:
        source = entity.get("source") if isinstance(entity.get("source"), dict) else {}
        for option in extract_control_options(
            str(entity.get("controlMeasures", "")), str(entity["id"]), str(entity.get("name", ""))
        ):
            candidates.append(
                {
                    "crop": str(entity.get("crop") or ""),
                    "diseaseId": str(entity["id"]),
                    "diseaseName": str(entity.get("name") or ""),
                    "controlName": str(option["name"]),
                    "controlType": str(option["type"]),
                    "relationType": "PREVENTS" if option["type"] == "AGRICULTURAL" else "CONTROLS",
                    "evidenceIds": list(option.get("evidenceIds") or []),
                    "sourceDatasetId": str(source.get("datasetId") or ""),
                    "sourceFile": str(source.get("file") or ""),
                    "sourceRow": source.get("row"),
                    "doi": str(source.get("doi") or ""),
                }
            )
    quotas = {
        ("番茄", "ACTIVE_INGREDIENT"): 8,
        ("番茄", "AGRICULTURAL"): 6,
        ("番茄", "BIOLOGICAL"): 1,
        ("水稻", "ACTIVE_INGREDIENT"): 7,
        ("水稻", "AGRICULTURAL"): 5,
        ("水稻", "BIOLOGICAL"): 3,
    }
    selected: list[dict[str, Any]] = []
    for (crop, kind), count in quotas.items():
        values = [row for row in candidates if row["crop"] == crop and row["controlType"] == kind]
        selected.extend(round_robin(values, count, "diseaseId"))
    selected.sort(key=lambda row: (row["crop"], row["controlType"], row["diseaseId"], row["controlName"]))
    return [
        {
            "caseId": f"CTRL-{index:03d}",
            **row,
            "goldReviewed": True,
            "goldReviewMethod": REVIEW_METHOD,
        }
        for index, row in enumerate(selected, 1)
    ]


def validate(images: list[dict[str, Any]], controls: list[dict[str, Any]]) -> None:
    if len(images) != 30 or len({row["imageId"] for row in images}) != 30:
        raise ValueError("图片评测集必须包含 30 张唯一图片")
    if sum(row["crop"] == "番茄" for row in images) != 15 or sum(row["crop"] == "水稻" for row in images) != 15:
        raise ValueError("图片评测集作物分层不正确")
    if len(controls) != 30 or len({(row["diseaseId"], row["controlName"], row["controlType"]) for row in controls}) != 30:
        raise ValueError("防治关系评测集必须包含 30 条唯一关系")
    if any(row["goldReviewMethod"] != REVIEW_METHOD for row in images + controls):
        raise ValueError("金标审核口径不正确")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", required=True)
    args = parser.parse_args()
    data_root = Path(args.data_root).resolve()
    knowledge = data_root / "processed" / "knowledge"
    entities = read_jsonl(knowledge / "agriculture-entities.jsonl")
    ontology = json.loads((ROOT / "config" / "ontology" / "agriculture-ontology.json").read_text(encoding="utf-8"))
    images = build_images(data_root, entities, ontology)
    controls = build_controls(entities)
    validate(images, controls)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUTPUT / "multimodal-image-test.jsonl", images)
    write_jsonl(OUTPUT / "control-relation-test.jsonl", controls)
    print(json.dumps({"images": len(images), "controlRelations": len(controls), "reviewMethod": REVIEW_METHOD}, ensure_ascii=False))


if __name__ == "__main__":
    main()
