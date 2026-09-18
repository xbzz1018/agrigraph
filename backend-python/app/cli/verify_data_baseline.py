"""验证 V2 Elasticsearch 与 Neo4j 数据基线，不输出凭据或正文。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from neo4j import GraphDatabase

from app.core.settings import Settings
from app.domain.control import contains_restricted_usage


def _has_dense_vector(value: Any) -> bool:
    if isinstance(value, dict):
        return value.get("type") == "dense_vector" or any(_has_dense_vector(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_dense_vector(item) for item in value)
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--env-file", default="")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    load_dotenv(root / ".env.ai", override=False)
    if args.env_file:
        load_dotenv(Path(args.env_file), override=True)
    settings = Settings.from_env()
    data_root = Path(args.data_root).resolve()
    entity_path = data_root / "processed" / "knowledge" / "agriculture-entities.jsonl"
    expected_entities = sum(bool(line.strip()) for line in entity_path.read_text(encoding="utf-8").splitlines())
    quality = json.loads((data_root / "processed" / "graph" / "quality-report.json").read_text(encoding="utf-8"))
    auth = (settings.es_username, settings.es_password) if settings.es_username else None
    with httpx.Client(base_url=settings.es_url, auth=auth, timeout=30) as client:
        count = client.get(f"/{settings.es_index}/_count")
        count.raise_for_status()
        es_count = int(count.json()["count"])
        mapping = client.get(f"/{settings.es_index}/_mapping")
        mapping.raise_for_status()
        source_count = client.post(
            f"/{settings.es_index}/_count", json={"query": {"prefix": {"fileMd5": "source-"}}}
        )
        source_count.raise_for_status()
        documents = client.post(
            f"/{settings.es_index}/_search",
            json={"size": 200, "_source": ["controlOptions", "controlPrinciples"], "query": {"match_all": {}}},
        )
        documents.raise_for_status()
        es_leaks = sum(
            contains_restricted_usage(json.dumps(hit.get("_source", {}), ensure_ascii=False))
            for hit in documents.json().get("hits", {}).get("hits", [])
        )
    driver = GraphDatabase.driver(
        settings.neo4j_url,
        auth=(settings.neo4j_username, settings.neo4j_password) if settings.neo4j_password else None,
        connection_timeout=5,
    )
    try:
        graph = driver.execute_query(
            "MATCH (n:Entity) WITH count(n) AS nodes "
            "MATCH ()-[r]->() RETURN nodes,count(r) AS relationships, "
            "sum(CASE WHEN type(r)='HAS_SYMPTOM' THEN 1 ELSE 0 END) AS hasSymptom, "
            "sum(CASE WHEN type(r)='CAUSED_BY' THEN 1 ELSE 0 END) AS causedBy, "
            "sum(CASE WHEN type(r)='FAVORED_BY' THEN 1 ELSE 0 END) AS favoredBy, "
            "sum(CASE WHEN type(r)='CONTROLS' THEN 1 ELSE 0 END) AS controls, "
            "sum(CASE WHEN type(r)='PREVENTS' THEN 1 ELSE 0 END) AS prevents"
        ).records[0]
        forbidden = driver.execute_query(
            "MATCH (n:Entity) RETURN count(CASE WHEN 'controlMeasures' IN keys(n) THEN 1 END) AS count"
        ).records[0]["count"]
        graph_leaks = driver.execute_query(
            "MATCH (n:Entity) WHERE n.type IN ['ActiveIngredient','BiologicalControl','AgriculturalPractice'] "
            "RETURN collect(coalesce(n.label,'')) AS labels"
        ).records[0]["labels"]
    finally:
        driver.close()
    checks = {
        "entitySourceCount": expected_entities == 158,
        "elasticsearchCount": es_count == expected_entities,
        "noSourceDocuments": int(source_count.json()["count"]) == 0,
        "noDenseVector": not _has_dense_vector(mapping.json()),
        "noElasticsearchUsageLeak": es_leaks == 0,
        "neo4jNodeCount": int(graph["nodes"]) == int(quality["nodes"]),
        "neo4jRelationshipCount": int(graph["relationships"]) == int(quality["edges"]),
        "coreRelations": all(int(graph[name]) > 0 for name in ("hasSymptom", "causedBy", "favoredBy", "controls", "prevents")),
        "noForbiddenGraphProperty": int(forbidden) == 0,
        "noGraphUsageLeak": not any(contains_restricted_usage(str(label)) for label in graph_leaks),
    }
    result = {
        "kind": "agrigraph-v2-data-baseline",
        "status": "PASSED" if all(checks.values()) else "FAILED",
        "index": settings.es_index,
        "counts": {
            "entities": es_count,
            "nodes": int(graph["nodes"]),
            "relationships": int(graph["relationships"]),
        },
        "relationCounts": {name: int(graph[name]) for name in ("hasSymptom", "causedBy", "favoredBy", "controls", "prevents")},
        "checks": checks,
    }
    if args.output:
        output = Path(args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
