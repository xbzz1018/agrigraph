"""Idempotently import prepared agricultural knowledge into Elasticsearch."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from app.core.settings import Settings
from app.domain.control import extract_control_options, extract_safe_control_principles


def _load_environment(extra_env: str = "") -> None:
    project_root = Path(__file__).resolve().parents[3]
    load_dotenv(project_root / ".env.ai", override=False)
    load_dotenv(project_root / "backend-python" / ".env", override=False)
    if extra_env:
        load_dotenv(Path(extra_env), override=True)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _entity_document(record: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    entity_id = str(record["id"])
    text_fields = (
        "summary",
        "symptoms",
        "pathogen",
        "infectionCycle",
        "occurrenceFactors",
        "habits",
        "morphology",
    )
    options = extract_control_options(str(record.get("controlMeasures", "")), entity_id, str(record.get("name", "")))
    principles = extract_safe_control_principles(str(record.get("controlMeasures", "")))
    option_names = [item["name"] for item in options]
    content_parts = [str(record.get(key, "")).strip() for key in text_fields if record.get(key)]
    if option_names:
        content_parts.append("防治选项：" + "、".join(option_names))
    if principles:
        content_parts.append("安全防治原则：" + principles)
    content = "\n".join(content_parts).strip()
    return entity_id, {
        "id": entity_id,
        "fileMd5": entity_id,
        "chunkId": entity_id,
        "name": str(record.get("name", "")),
        "title": str(record.get("name", "")),
        "crop": str(record.get("crop", "")),
        "entityType": str(record.get("entityType", "")),
        "entityTypeCode": str(record.get("entityTypeCode", "")),
        "summary": str(record.get("summary", "")),
        "symptoms": str(record.get("symptoms", "")),
        "pathogen": str(record.get("pathogen", "")),
        "occurrenceFactors": str(record.get("occurrenceFactors", "")),
        "affectedParts": record.get("affectedParts", []),
        "aliases": record.get("aliases", []),
        "content": content,
        "controlOptions": options,
        "controlPrinciples": principles,
        "source": record.get("source", {}),
        "ingestSource": "agrigraph-prepared-entity",
    }


def load_documents(data_root: Path) -> list[tuple[str, dict[str, Any]]]:
    knowledge_root = data_root / "processed" / "knowledge"
    entities = [_entity_document(row) for row in _read_jsonl(knowledge_root / "agriculture-entities.jsonl")]
    identifiers = [item[0] for item in entities]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Prepared knowledge contains duplicate document IDs")
    return entities


def _mapping(settings: Settings) -> dict[str, Any]:
    return {
        "mappings": {
            "properties": {
                "id": {"type": "keyword"},
                "fileMd5": {"type": "keyword"},
                "chunkId": {"type": "keyword"},
                "crop": {"type": "keyword"},
                "entityTypeCode": {"type": "keyword"},
                "name": {"type": "text"},
                "title": {"type": "text"},
                "summary": {"type": "text"},
                "symptoms": {"type": "text"},
                "pathogen": {"type": "text"},
                "occurrenceFactors": {"type": "text"},
                "affectedParts": {"type": "text"},
                "aliases": {"type": "text"},
                "content": {"type": "text"},
                "controlPrinciples": {"type": "text"},
                "controlOptions": {
                    "properties": {
                        "name": {"type": "keyword"},
                        "type": {"type": "keyword"},
                        "targetDiseaseId": {"type": "keyword"},
                        "targetDiseaseName": {"type": "keyword"},
                        "evidenceIds": {"type": "keyword"},
                    }
                },
            }
        }
    }


def _ensure_index(client: httpx.Client, settings: Settings) -> None:
    response = client.head(f"/{settings.es_index}")
    if response.status_code == 404:
        client.put(f"/{settings.es_index}", json=_mapping(settings)).raise_for_status()
        return
    response.raise_for_status()
    client.put(f"/{settings.es_index}/_mapping", json=_mapping(settings)["mappings"]).raise_for_status()


def _recreate_index(client: httpx.Client, settings: Settings) -> None:
    if settings.es_index != "agrigraph_evidence_v2":
        raise RuntimeError("Refusing to recreate an index outside the managed V2 acceptance namespace")
    response = client.head(f"/{settings.es_index}")
    if response.status_code == 200:
        client.delete(f"/{settings.es_index}").raise_for_status()
    elif response.status_code != 404:
        response.raise_for_status()
    client.put(f"/{settings.es_index}", json=_mapping(settings)).raise_for_status()


def _bulk_import(
    client: httpx.Client, settings: Settings, documents: list[tuple[str, dict[str, Any]]], batch_size: int
) -> int:
    imported = 0
    for offset in range(0, len(documents), batch_size):
        lines: list[str] = []
        for document_id, source in documents[offset : offset + batch_size]:
            lines.append(json.dumps({"index": {"_index": settings.es_index, "_id": document_id}}))
            lines.append(json.dumps(source, ensure_ascii=False))
        response = client.post(
            "/_bulk?refresh=wait_for",
            content="\n".join(lines) + "\n",
            headers={"Content-Type": "application/x-ndjson"},
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("errors"):
            failures = sum(bool(item.get("index", {}).get("error")) for item in payload.get("items", []))
            raise RuntimeError(f"Elasticsearch bulk import failed for {failures} documents")
        imported += len(documents[offset : offset + batch_size])
    return imported


def main() -> None:
    parser = argparse.ArgumentParser(description="Import prepared AgriGraph documents into Elasticsearch.")
    parser.add_argument("--data-root", default="")
    parser.add_argument("--env-file", default="")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--recreate-index", action="store_true")
    args = parser.parse_args()
    if args.batch_size < 1 or args.batch_size > 1000:
        parser.error("batch-size must be 1..1000")

    _load_environment(args.env_file)
    data_root = args.data_root or os.getenv("AGRIGRAPH_DATA_ROOT", "")
    if not data_root:
        parser.error("set --data-root or AGRIGRAPH_DATA_ROOT")
    settings = Settings.from_env()
    documents = load_documents(Path(data_root))
    entity_count = len(documents)
    if args.dry_run:
        imported = 0
    else:
        auth = (settings.es_username, settings.es_password) if settings.es_username else None
        with httpx.Client(base_url=settings.es_url, auth=auth, timeout=30) as client:
            if args.recreate_index:
                _recreate_index(client, settings)
            else:
                _ensure_index(client, settings)
            imported = _bulk_import(client, settings, documents, args.batch_size)
    print(
        json.dumps(
            {
                "status": "DRY_RUN" if args.dry_run else "COMPLETED",
                "index": settings.es_index,
                "documents": len(documents),
                "entities": entity_count,
                "imported": imported,
                "retrieval": "bm25",
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
