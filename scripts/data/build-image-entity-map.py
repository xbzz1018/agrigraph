"""为精选图片生成用途分类、实体映射和质量报告。"""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter, defaultdict
from pathlib import Path


def _data_root() -> Path:
    value = os.environ.get("AGRIGRAPH_DATA_ROOT", "").strip()
    if not value:
        raise RuntimeError("请先设置 AGRIGRAPH_DATA_ROOT，数据必须位于源码目录之外")
    return Path(value).expanduser().resolve()


DATA_ROOT = _data_root()
PROJECT_ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_ROOT = DATA_ROOT / "processed/knowledge"
OUTPUT = KNOWLEDGE_ROOT / "image-entity-map.jsonl"
REPORT = DATA_ROOT / "manifests/image-quality-report.json"
ALIAS_CONFIG = PROJECT_ROOT / "config/ontology/image-entity-aliases.json"
DATASET_CONFIG = PROJECT_ROOT / "config/datasets/agrigraph-datasets.json"
ALLOWED_LICENSE_PREFIXES = ("CC0", "CC BY ", "CC BY-SA ", "Public domain")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_entity(expected: str, entities: list[dict]) -> dict | None:
    for entity in entities:
        names = {entity.get("name", ""), *entity.get("aliases", [])}
        if expected in names:
            return entity
    return None


def license_allowed(value: str) -> bool:
    return any(value.lower().startswith(prefix.lower()) for prefix in ALLOWED_LICENSE_PREFIXES)


def classify(row: dict, aliases: list[dict], entities: list[dict], licenses: dict[str, str]) -> dict:
    if row.get("verificationStatus") == "VERIFIED" and row.get("entityId"):
        thumbnail = DATA_ROOT / str(row.get("thumbnailFile", ""))
        return {
            **row,
            "sha256": row.get("sha256") or (file_sha256(thumbnail) if thumbnail.is_file() else ""),
        }
    source_file = str(row.get("sourceFile", "")).replace("\\", "/")
    lower_path = source_file.lower()
    dataset_id = row.get("datasetId", "")
    license_name = row.get("license") or licenses.get(dataset_id, "")
    usage = "CROP_REFERENCE"
    status = "UNVERIFIED"
    entity: dict | None = None
    matched_token = ""

    for alias in aliases:
        if alias["token"].lower() in lower_path:
            entity = resolve_entity(alias["entity"], entities)
            if entity:
                usage = alias["usage"]
                status = "VERIFIED" if license_allowed(license_name) else "LICENSE_MISSING"
                matched_token = alias["token"]
                break

    if row.get("stage") or dataset_id in {"rice-phenology", "crop-phenology-images", "tomato-growth-stages"}:
        usage = "GROWTH_STAGE"
        status = "VERIFIED" if license_allowed(license_name) else "LICENSE_MISSING"
        entity = None
    elif dataset_id == "tomato-leaf-disease" and entity is None:
        usage = "CROP_REFERENCE"
        status = "UNVERIFIED"

    thumbnail = DATA_ROOT / str(row.get("thumbnailFile", ""))
    return {
        **row,
        "usage": usage,
        "verificationStatus": status,
        "entityId": entity.get("id", "") if entity else "",
        "entityName": entity.get("name", "") if entity else "",
        "entityType": entity.get("entityTypeCode", "") if entity else "",
        "matchedToken": matched_token,
        "license": license_name,
        "sha256": row.get("sha256") or (file_sha256(thumbnail) if thumbnail.is_file() else ""),
    }


def main() -> None:
    aliases = json.loads(ALIAS_CONFIG.read_text(encoding="utf-8"))["aliases"]
    datasets = json.loads(DATASET_CONFIG.read_text(encoding="utf-8"))["datasets"]
    licenses = {item["id"]: item.get("license", "") for item in datasets}
    entities = read_jsonl(KNOWLEDGE_ROOT / "agriculture-entities.jsonl")
    images = read_jsonl(KNOWLEDGE_ROOT / "image-curated.jsonl")
    images += read_jsonl(KNOWLEDGE_ROOT / "tomato-growth-images.jsonl")
    images += read_jsonl(KNOWLEDGE_ROOT / "supplemental-images.jsonl")
    mapped = [classify(row, aliases, entities, licenses) for row in images]

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8", newline="\n") as stream:
        for row in mapped:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")

    coverage: dict[str, Counter] = defaultdict(Counter)
    for row in mapped:
        if row["entityName"]:
            coverage[row["entityName"]]["images"] += 1
    report = {
        "total": len(mapped),
        "byUsage": dict(Counter(row["usage"] for row in mapped)),
        "byStatus": dict(Counter(row["verificationStatus"] for row in mapped)),
        "verifiedEntityImages": sum(bool(row["entityId"]) and row["verificationStatus"] == "VERIFIED" for row in mapped),
        "mappedEntities": len(coverage),
        "damaged": sum(not (DATA_ROOT / str(row.get("thumbnailFile", ""))).is_file() for row in mapped),
        "licenseMissing": sum(row["verificationStatus"] == "LICENSE_MISSING" for row in mapped),
        "entityCoverage": {name: dict(value) for name, value in sorted(coverage.items())},
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
