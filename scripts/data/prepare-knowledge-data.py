"""将农业原始资料整理为 GraphRAG 可使用的统一 JSONL，不修改 raw 数据。"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup
from rdflib import Graph
from rdflib.namespace import RDFS, SKOS


def _data_root() -> Path:
    value = os.environ.get("AGRIGRAPH_DATA_ROOT", "").strip()
    if not value:
        raise RuntimeError("请先设置 AGRIGRAPH_DATA_ROOT，数据必须位于源码目录之外")
    return Path(value).expanduser().resolve()


DATA_ROOT = _data_root()
RAW_ROOT = DATA_ROOT / "raw"
OUTPUT_ROOT = DATA_ROOT / "processed" / "knowledge"
REPORT_ROOT = DATA_ROOT / "logs"

SOURCE_DATASET_ID = "0b117cc43bf44b70ab2dc567c84641cc"
SOURCE_DOI = "10.57760/sciencedb.agriculture.00187"
SOURCE_LICENSE = "CC0 1.0"
SOURCE_URL = (
    "https://agri.scidb.cn/detail?dataSetId="
    "0b117cc43bf44b70ab2dc567c84641cc"
)

SPREADSHEETS = (
    ("tomato", "disease", RAW_ROOT / "agriculture-text/tomato/tomato-disease.xlsx"),
    ("tomato", "pest", RAW_ROOT / "agriculture-text/tomato/tomato-pest.xlsx"),
    ("rice", "disease", RAW_ROOT / "agriculture-text/rice/rice-disease.xls"),
    ("rice", "pest", RAW_ROOT / "agriculture-text/rice/rice-pest.xls"),
)

IMAGE_DATASETS = (
    ("tomato-multimodal", RAW_ROOT / "tomato-multimodal"),
    ("tomato-leaf-disease", RAW_ROOT / "tomato-leaf-disease"),
    ("rice-phenology", RAW_ROOT / "rice-phenology"),
    ("crop-phenology-images", RAW_ROOT / "crop-phenology-images"),
)
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}

CROP_NAMES = {"tomato": "番茄", "rice": "水稻"}
TYPE_NAMES = {"disease": "病害", "pest": "虫害"}
FIELD_MAP = {
    "中文名称": "name",
    "简介": "summary",
    "危害症状": "symptoms",
    "病原": "pathogen",
    "侵染循环": "infectionCycle",
    "发生因素": "occurrenceFactors",
    "生活习性": "habits",
    "形态特征": "morphology",
    "防治方法": "controlMeasures",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def normalize_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).replace("\u3000", " ").replace("\xa0", " ")
    return re.sub(r"[ \t]+", " ", text).strip()


def stable_id(crop: str, entity_type: str, name: str) -> str:
    source = f"{crop}:{entity_type}:{name}".encode()
    return hashlib.sha256(source).hexdigest()[:24]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_spreadsheets() -> tuple[list[dict], list[dict]]:
    entities: list[dict] = []
    quality: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    for crop, entity_type, path in SPREADSHEETS:
        if not path.exists():
            quality.append({"file": str(path), "status": "missing"})
            continue

        frame = pd.read_excel(path, sheet_name=0).dropna(how="all")
        source_hash = sha256(path)
        duplicate_names = int(frame["中文名称"].astype(str).duplicated().sum())
        quality.append(
            {
                "file": str(path),
                "status": "parsed",
                "rows": len(frame),
                "columns": [str(column) for column in frame.columns],
                "duplicateNames": duplicate_names,
                "sha256": source_hash,
            }
        )

        for row_number, source_row in frame.iterrows():
            normalized = {
                target: normalize_text(source_row.get(source))
                for source, target in FIELD_MAP.items()
            }
            name = normalized.pop("name")
            if not name:
                quality.append(
                    {"file": str(path), "row": int(row_number) + 2, "status": "missing-name"}
                )
                continue
            identity = (crop, entity_type, name)
            if identity in seen:
                continue
            seen.add(identity)
            entities.append(
                {
                    "id": stable_id(crop, entity_type, name),
                    "crop": CROP_NAMES[crop],
                    "cropCode": crop,
                    "entityType": TYPE_NAMES[entity_type],
                    "entityTypeCode": entity_type,
                    "name": name,
                    **normalized,
                    "source": {
                        "datasetId": SOURCE_DATASET_ID,
                        "doi": SOURCE_DOI,
                        "license": SOURCE_LICENSE,
                        "url": SOURCE_URL,
                        "file": str(path.relative_to(DATA_ROOT)).replace("\\", "/"),
                        "sha256": source_hash,
                        "row": int(row_number) + 2,
                    },
                }
            )
    return entities, quality


def parse_html_documents() -> list[dict]:
    documents: list[dict] = []
    roots = (RAW_ROOT / "agriculture-text", RAW_ROOT / "agriculture-standards")
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.html")):
            raw = path.read_bytes()
            text = ""
            for encoding in ("utf-8", "gb18030"):
                try:
                    text = raw.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            soup = BeautifulSoup(text, "html.parser")
            for element in soup(["script", "style", "noscript"]):
                element.decompose()
            content = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n", strip=True))
            documents.append(
                {
                    "id": hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:24],
                    "title": soup.title.get_text(strip=True) if soup.title else path.stem,
                    "content": content,
                    "sourceFile": str(path.relative_to(DATA_ROOT)).replace("\\", "/"),
                    "sha256": sha256(path),
                }
            )
    return documents


def parse_ontology() -> list[dict]:
    path = RAW_ROOT / "agriculture-ontology/plant-ontology.owl"
    if not path.exists():
        return []
    graph = Graph()
    graph.parse(path)
    concepts: list[dict] = []
    for subject in set(graph.subjects(RDFS.label, None)) | set(graph.subjects(SKOS.prefLabel, None)):
        labels = {
            str(label).strip()
            for label in list(graph.objects(subject, RDFS.label))
            + list(graph.objects(subject, SKOS.prefLabel))
            if str(label).strip()
        }
        if labels:
            concepts.append({"uri": str(subject), "labels": sorted(labels)})
    return sorted(concepts, key=lambda item: item["uri"])


def parse_image_inventory() -> list[dict]:
    images: list[dict] = []
    for dataset_id, root in IMAGE_DATASETS:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            relative = str(path.relative_to(DATA_ROOT)).replace("\\", "/")
            path_parts = {part.lower() for part in path.parts}
            source_split = next(
                (name for name in ("train", "valid", "validation", "test") if name in path_parts),
                "",
            )
            images.append(
                {
                    "id": hashlib.sha256(relative.encode("utf-8")).hexdigest()[:24],
                    "datasetId": dataset_id,
                    "sourceFile": relative,
                    "extension": path.suffix.lower(),
                    "sizeBytes": path.stat().st_size,
                    # 仅记录发布方原目录名，不作为本项目的训练或验证划分。
                    "sourceSplit": source_split,
                    "usage": "knowledge-case",
                }
            )
    return images


def main() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    entities, quality = parse_spreadsheets()
    documents = parse_html_documents()
    ontology = parse_ontology()
    images = parse_image_inventory()

    write_jsonl(OUTPUT_ROOT / "agriculture-entities.jsonl", entities)
    write_jsonl(OUTPUT_ROOT / "source-documents.jsonl", documents)
    write_jsonl(OUTPUT_ROOT / "plant-ontology.jsonl", ontology)
    write_jsonl(OUTPUT_ROOT / "image-inventory.jsonl", images)

    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "dataRoot": str(DATA_ROOT),
        "entityCount": len(entities),
        "documentCount": len(documents),
        "ontologyConceptCount": len(ontology),
        "imageCount": len(images),
        "imagesByDataset": {
            dataset_id: sum(item["datasetId"] == dataset_id for item in images)
            for dataset_id, _ in IMAGE_DATASETS
        },
        "byCropAndType": {
            f"{crop}:{entity_type}": sum(
                item["cropCode"] == crop and item["entityTypeCode"] == entity_type
                for item in entities
            )
            for crop, entity_type, _ in SPREADSHEETS
        },
        "quality": quality,
    }
    report_path = REPORT_ROOT / "knowledge-data-quality.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
