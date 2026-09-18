"""清洗农业实体并生成可幂等执行的 Neo4j CSV/Cypher 导入文件。"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sys
from pathlib import Path

from rdflib import Graph, URIRef
from rdflib.namespace import RDFS

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend-python"))

from app.domain.control import extract_control_options  # noqa: E402


def _data_root() -> Path:
    value = os.environ.get("AGRIGRAPH_DATA_ROOT", "").strip()
    if not value:
        raise RuntimeError("请先设置 AGRIGRAPH_DATA_ROOT，数据必须位于源码目录之外")
    return Path(value).expanduser().resolve()


DATA_ROOT = _data_root()
SOURCE = DATA_ROOT / "processed/knowledge/agriculture-entities.jsonl"
OUTPUT = DATA_ROOT / "processed/graph"
ONTOLOGY = PROJECT_ROOT / "config/ontology/agriculture-ontology.json"

NODE_FIELDS = [
    "id", "label", "type", "aliases", "summary", "symptoms", "pathogen",
    "occurrenceFactors", "controlOptions", "datasetId",
    "doi", "license", "sourceFile", "sourceRow", "imageObjectKey", "thumbnailObjectKey",
    "imageSource", "sourceDatasetId", "sourcePage", "artist", "licenseUrl", "stage",
    "usage", "verificationStatus", "entityName", "sha256",
]
EDGE_FIELDS = ["id", "source", "target", "type", "label", "datasetId", "doi", "evidence"]


def identifier(*parts: str) -> str:
    return hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()[:24]


def clean_name(value: str) -> str:
    value = re.sub(r"\s+", "", value or "")
    return value.replace("（", "(").replace("）", ")").strip()


def aliases(crop: str, name: str) -> list[str]:
    result = {name}
    if name.startswith(crop) and len(name) > len(crop) + 1:
        result.add(name[len(crop):])
    return sorted(result)


def pathogen_name(text: str) -> str:
    if not text:
        return ""
    value = re.split(r"[，。；;]", text, maxsplit=1)[0]
    value = re.sub(r"^病原(?:为|是)?", "", value).strip()
    return value[:180]


def add_node(nodes: dict[str, dict], node: dict) -> None:
    for field in NODE_FIELDS:
        node.setdefault(field, "")
    current = nodes.get(node["id"])
    if current is None:
        nodes[node["id"]] = node
        return
    current_aliases = set(filter(None, current.get("aliases", "").split("|")))
    current_aliases.update(filter(None, node.get("aliases", "").split("|")))
    current["aliases"] = "|".join(sorted(current_aliases))


def add_edge(edges: dict[str, dict], source: str, target: str, edge_type: str,
             label: str, dataset_id: str, doi: str, evidence: str) -> None:
    edge_id = identifier(source, edge_type, target)
    edges.setdefault(edge_id, {
        "id": edge_id,
        "source": source,
        "target": target,
        "type": edge_type,
        "label": label,
        "datasetId": dataset_id,
        "doi": doi,
        "evidence": evidence[:1000],
    })


def sections(text: str) -> list[str]:
    value = (text or "").strip()
    if not value:
        return []
    parts = [part.strip() for part in re.split(r"(?=\([1-9]\d*\))", value) if part.strip()]
    return parts if len(parts) > 1 else [value]


def short_label(text: str, fallback: str) -> str:
    label = re.sub(r"^\([1-9]\d*\)", "", text).strip()
    label = re.split(r"[。；;：:]", label, maxsplit=1)[0].strip()
    return label[:42] or fallback


def main() -> None:
    if not SOURCE.exists():
        raise FileNotFoundError(f"请先生成农业实体：{SOURCE}")
    ontology = json.loads(ONTOLOGY.read_text(encoding="utf-8"))
    records = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines()]
    nodes: dict[str, dict] = {}
    edges: dict[str, dict] = {}

    dataset_id = "dataset-agricultural-information-retrieval"
    add_node(nodes, {
        "id": dataset_id, "label": "农业信息检索数据集", "type": "Dataset", "aliases": "",
        "summary": "番茄和水稻病虫害结构化知识来源", "symptoms": "", "pathogen": "",
        "occurrenceFactors": "", "controlOptions": "",
        "datasetId": "0b117cc43bf44b70ab2dc567c84641cc",
        "doi": "10.57760/sciencedb.agriculture.00187", "license": "CC0 1.0",
        "sourceFile": "", "sourceRow": "",
    })

    entities_by_alias: list[tuple[str, str]] = []

    for record in records:
        crop_name = clean_name(record["crop"])
        crop_id = identifier("crop", crop_name)
        add_node(nodes, {
            "id": crop_id, "label": crop_name, "type": "Crop", "aliases": crop_name,
            "summary": "", "symptoms": "", "pathogen": "", "occurrenceFactors": "",
            "controlOptions": "", "datasetId": "",
            "doi": "", "license": "", "sourceFile": "", "sourceRow": "",
        })
        name = clean_name(record["name"])
        entity_type = "Disease" if record["entityTypeCode"] == "disease" else "Pest"
        # ES、评测金标和 Neo4j 必须共享公开实体主键，不能按名称重新生成第二套 ID。
        entity_id = str(record["id"])
        source = record["source"]
        control_options = extract_control_options(record.get("controlMeasures", ""), entity_id, name)
        add_node(nodes, {
            "id": entity_id, "label": name, "type": entity_type,
            "aliases": "|".join(aliases(crop_name, name)),
            "summary": record.get("summary", ""), "symptoms": record.get("symptoms", ""),
            "pathogen": record.get("pathogen", ""),
            "occurrenceFactors": record.get("occurrenceFactors", ""),
            "controlOptions": "|".join(item["name"] for item in control_options),
            "datasetId": source["datasetId"], "doi": source["doi"], "license": source["license"],
            "sourceFile": source["file"], "sourceRow": source["row"],
        })
        for alias in aliases(crop_name, name):
            if len(alias) >= 3:
                entities_by_alias.append((alias, entity_id))
        relation = "HAS_DISEASE" if entity_type == "Disease" else "HAS_PEST"
        add_edge(edges, crop_id, entity_id, relation, "病害" if entity_type == "Disease" else "虫害",
                 source["datasetId"], source["doi"], record.get("summary", ""))
        add_edge(edges, entity_id, dataset_id, "DERIVED_FROM", "来源", source["datasetId"],
                 source["doi"], f"{source['file']} 第{source['row']}行")

        pathogen = pathogen_name(record.get("pathogen", ""))
        if pathogen:
            pathogen_id = identifier("pathogen", pathogen)
            add_node(nodes, {
                "id": pathogen_id, "label": pathogen, "type": "Pathogen", "aliases": pathogen,
                "summary": record.get("pathogen", ""), "symptoms": "", "pathogen": "",
                "occurrenceFactors": "", "controlOptions": "",
                "datasetId": source["datasetId"], "doi": source["doi"], "license": source["license"],
                "sourceFile": source["file"], "sourceRow": source["row"],
            })
            add_edge(edges, entity_id, pathogen_id, "CAUSED_BY", "病原", source["datasetId"],
                     source["doi"], record.get("pathogen", ""))
            for pathogen_type in ("真菌", "细菌", "病毒", "线虫", "原生生物"):
                if pathogen_type not in record.get("pathogen", ""):
                    continue
                type_id = identifier("pathogen-type", pathogen_type)
                add_node(nodes, {"id": type_id, "label": pathogen_type, "type": "PathogenType", "aliases": pathogen_type})
                add_edge(edges, pathogen_id, type_id, "IS_PATHOGEN_TYPE", "病原类型",
                         source["datasetId"], source["doi"], record.get("pathogen", ""))

        factors_text = record.get("occurrenceFactors", "")
        for factor, keywords in ontology["environmentFactors"].items():
            if not any(keyword in factors_text for keyword in keywords):
                continue
            factor_id = identifier("environment", factor)
            add_node(nodes, {
                "id": factor_id, "label": factor, "type": "EnvironmentFactor", "aliases": factor,
                "summary": "", "symptoms": "", "pathogen": "", "occurrenceFactors": "",
                "controlOptions": "", "datasetId": "",
                "doi": "", "license": "", "sourceFile": "", "sourceRow": "",
            })
            add_edge(edges, entity_id, factor_id, "FAVORED_BY", "发生条件", source["datasetId"],
                     source["doi"], factors_text)

        for match in re.findall(r"\d+(?:\.\d+)?\s*(?:～|~|-)\s*\d+(?:\.\d+)?\s*(?:℃|%)|\d+(?:\.\d+)?\s*%以上", factors_text):
            threshold = re.sub(r"\s+", "", match)
            threshold_id = identifier("environment-threshold", threshold)
            add_node(nodes, {
                "id": threshold_id, "label": threshold, "type": "EnvironmentThreshold",
                "aliases": threshold, "summary": factors_text, "datasetId": source["datasetId"],
                "doi": source["doi"], "license": source["license"],
            })
            add_edge(edges, entity_id, threshold_id, "HAS_THRESHOLD", "环境阈值",
                     source["datasetId"], source["doi"], factors_text)

        symptom_text_all = record.get("symptoms", "")
        normalized_symptom_ids: list[str] = []
        for symptom, keywords in ontology["symptoms"].items():
            if not any(keyword in symptom_text_all for keyword in keywords):
                continue
            normalized_id = identifier("normalized-symptom", symptom)
            normalized_symptom_ids.append(normalized_id)
            add_node(nodes, {"id": normalized_id, "label": symptom, "type": "Symptom", "aliases": symptom})
            add_edge(edges, entity_id, normalized_id, "HAS_SYMPTOM", "规范症状",
                     source["datasetId"], source["doi"], symptom_text_all)

        for part, keywords in ontology["plantParts"].items():
            if not any(keyword in symptom_text_all for keyword in keywords):
                continue
            part_id = identifier("plant-part", part)
            add_node(nodes, {"id": part_id, "label": part, "type": "PlantPart", "aliases": part})
            add_edge(edges, entity_id, part_id, "AFFECTS_PART", "危害部位",
                     source["datasetId"], source["doi"], symptom_text_all)
            for symptom_id in normalized_symptom_ids:
                add_edge(edges, symptom_id, part_id, "OCCURS_ON", "发生部位",
                         source["datasetId"], source["doi"], symptom_text_all)

        for index, symptom_text in enumerate(sections(record.get("symptoms", "")), start=1):
            symptom_id = identifier("symptom", entity_id, str(index))
            add_node(nodes, {
                "id": symptom_id, "label": short_label(symptom_text, f"{name}症状{index}"),
                "type": "Symptom", "aliases": "", "summary": symptom_text,
                "datasetId": source["datasetId"], "doi": source["doi"],
                "license": source["license"], "sourceFile": source["file"], "sourceRow": source["row"],
            })
            add_edge(edges, entity_id, symptom_id, "HAS_SYMPTOM", "症状", source["datasetId"],
                     source["doi"], symptom_text)

        for option in control_options:
            option_type = {
                "ACTIVE_INGREDIENT": "ActiveIngredient",
                "BIOLOGICAL": "BiologicalControl",
                "AGRICULTURAL": "AgriculturalPractice",
            }[option["type"]]
            option_id = identifier(option_type.lower(), option["name"])
            add_node(nodes, {
                "id": option_id,
                "label": option["name"],
                "type": option_type,
                "aliases": option["name"],
                "summary": "",
                "controlOptions": option["name"],
                "datasetId": source["datasetId"],
                "doi": source["doi"],
                "license": source["license"],
                "sourceFile": source["file"],
                "sourceRow": source["row"],
            })
            relation = "PREVENTS" if option["type"] == "AGRICULTURAL" else "CONTROLS"
            add_edge(
                edges,
                option_id,
                entity_id,
                relation,
                "预防" if relation == "PREVENTS" else "防治",
                source["datasetId"],
                source["doi"],
                option["name"],
            )

        evidence_id = identifier("evidence", entity_id, source["file"], str(source["row"]))
        add_node(nodes, {
            "id": evidence_id, "label": f"{name}数据证据", "type": "Evidence", "aliases": "",
            "summary": record.get("summary", ""), "datasetId": source["datasetId"],
            "doi": source["doi"], "license": source["license"], "sourceFile": source["file"],
            "sourceRow": source["row"],
        })
        add_edge(edges, entity_id, evidence_id, "EVIDENCED_BY", "证据", source["datasetId"],
                 source["doi"], f"{source['file']} 第{source['row']}行")

    image_map = DATA_ROOT / "processed/knowledge/image-entity-map.jsonl"
    image_manifests = [image_map] if image_map.exists() else [
        DATA_ROOT / "processed/knowledge/image-curated.jsonl",
        DATA_ROOT / "processed/knowledge/tomato-growth-images.jsonl",
    ]
    if any(path.exists() for path in image_manifests):
        entities_by_alias.sort(key=lambda item: len(item[0]), reverse=True)
        crop_nodes: dict[str, str] = {
            row["label"]: row["id"] for row in nodes.values() if row["type"] == "Crop"
        }
        disease_nodes = {row["label"]: row["id"] for row in nodes.values() if row["type"] == "Disease"}
        agriculture_nodes = {
            (row["label"], row["type"]): row["id"]
            for row in nodes.values() if row["type"] in {"Disease", "Pest"}
        }
        filename_diseases = {
            "early-blight": "番茄早疫病", "early_blight": "番茄早疫病",
            "late-blight": "番茄晚疫病", "late_blight": "番茄晚疫病",
            "septoria": "番茄斑枯病", "leaf-mold": "番茄叶霉病", "leaf_mold": "番茄叶霉病",
            "bacterial-spot": "番茄细菌性斑点病", "yellow-leaf-curl": "番茄黄化曲叶病毒病",
        }
        image_rows = [json.loads(line) for manifest in image_manifests if manifest.exists()
                      for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
        for image in image_rows:
            path = image["sourceFile"]
            target_id = ""
            if image.get("verificationStatus") == "VERIFIED" and image.get("usage") in {"DISEASE_CASE", "PEST_CASE"}:
                entity_type = "Disease" if image.get("usage") == "DISEASE_CASE" else "Pest"
                target_id = agriculture_nodes.get((image.get("entityName", ""), entity_type), "")
            if not image_map.exists():
                target_id = next((entity for alias, entity in entities_by_alias if alias in path), "")
            lower_path = path.lower()
            if not target_id and not image_map.exists():
                target_id = next((disease_nodes.get(label, "") for token, label in filename_diseases.items()
                                  if token in lower_path and disease_nodes.get(label)), "")
            crop_name = image.get("crop") or ("番茄" if image["datasetId"].startswith("tomato") else "水稻")
            stage_match = re.search(r"/\d{2}([^/]+期)/", path)
            if image["datasetId"] == "crop-phenology-images":
                crop_match = re.search(r"/\d{2}([^/]+)/\d{2}", path)
                if crop_match:
                    crop_name = crop_match.group(1)
            if crop_name not in crop_nodes:
                crop_id = identifier("crop", crop_name)
                add_node(nodes, {"id": crop_id, "label": crop_name, "type": "Crop", "aliases": crop_name})
                crop_nodes[crop_name] = crop_id
            if not target_id:
                target_id = crop_nodes[crop_name]

            image_id = "image-" + image["id"]
            add_node(nodes, {
                "id": image_id, "label": Path(path).name, "type": "ImageCase", "aliases": "",
                "summary": "精选农业图片案例", "sourceFile": path,
                "imageObjectKey": image["thumbnailFile"],
                "thumbnailObjectKey": image["thumbnailFile"], "imageSource": path,
                "sourceDatasetId": image["datasetId"], "datasetId": image["datasetId"],
                "license": image.get("license", ""), "sourcePage": image.get("sourcePage", ""),
                "artist": image.get("artist", ""), "licenseUrl": image.get("licenseUrl", ""),
                "stage": image.get("stage", ""), "usage": image.get("usage", "CROP_REFERENCE"),
                "verificationStatus": image.get("verificationStatus", "UNVERIFIED"),
                "entityName": image.get("entityName", ""), "sha256": image.get("sha256", ""),
            })
            add_edge(edges, target_id, image_id, "HAS_IMAGE", "图片案例", image["datasetId"], "", path)

            if stage_match:
                stage = stage_match.group(1)
                stage_id = identifier("growth-stage", crop_name, stage)
                add_node(nodes, {
                    "id": stage_id, "label": stage, "type": "GrowthStage", "aliases": stage,
                    "sourceDatasetId": image["datasetId"], "datasetId": image["datasetId"],
                })
                add_edge(edges, crop_nodes[crop_name], stage_id, "HAS_GROWTH_STAGE", "生育期",
                         image["datasetId"], "", path)
                add_edge(edges, stage_id, image_id, "HAS_IMAGE", "阶段图片", image["datasetId"], "", path)

    ontology_path = DATA_ROOT / "raw/agriculture-ontology/plant-ontology.owl"
    if ontology_path.exists():
        graph = Graph()
        graph.parse(ontology_path)
        terms = {"leaf", "root", "stem", "flower", "fruit", "seed", "inflorescence", "plant organ"}
        exact = {subject for subject, label in graph.subject_objects(RDFS.label)
                 if str(label).lower() in terms and "obsolete" not in str(label).lower()}
        related = sorted({subject for subject, label in graph.subject_objects(RDFS.label)
                          if any(term in str(label).lower() for term in terms)
                          and "obsolete" not in str(label).lower()}, key=str)[:250]
        selected = exact | set(related)
        selected |= {parent for child in list(selected) for parent in graph.objects(child, RDFS.subClassOf)
                     if isinstance(parent, URIRef)}
        for subject in sorted(selected, key=str):
            labels = [str(value) for value in graph.objects(subject, RDFS.label)]
            if not labels:
                continue
            concept_id = identifier("plant-ontology", str(subject))
            add_node(nodes, {"id": concept_id, "label": labels[0], "type": "OntologyConcept",
                             "aliases": "|".join(sorted(set(labels))), "summary": str(subject),
                             "sourceDatasetId": "plant-ontology"})
            for parent in graph.objects(subject, RDFS.subClassOf):
                if parent not in selected:
                    continue
                parent_id = identifier("plant-ontology", str(parent))
                add_edge(edges, concept_id, parent_id, "IS_A", "本体上位概念", "plant-ontology", "", str(subject))

        part_mapping = {"叶片": "leaf", "根": "root", "茎": "stem", "花": "flower",
                        "果实": "fruit", "种子": "seed", "穗": "inflorescence"}
        labels_to_id = {row["label"].lower(): row["id"] for row in nodes.values()
                        if row["type"] == "OntologyConcept"}
        for part, english in part_mapping.items():
            part_id = identifier("plant-part", part)
            if part_id in nodes and english in labels_to_id:
                add_edge(edges, part_id, labels_to_id[english], "MAPS_TO_ONTOLOGY", "本体映射",
                         "plant-ontology", "", english)

    OUTPUT.mkdir(parents=True, exist_ok=True)
    valid_edges = {edge_id: row for edge_id, row in edges.items()
                   if row["source"] in nodes and row["target"] in nodes}
    linked_ids = {row["source"] for row in valid_edges.values()} | {row["target"] for row in valid_edges.values()}
    nodes = {node_id: row for node_id, row in nodes.items()
             if row["type"] != "OntologyConcept" or node_id in linked_ids}
    valid_edges = {edge_id: row for edge_id, row in valid_edges.items()
                   if row["source"] in nodes and row["target"] in nodes}
    node_rows = sorted(nodes.values(), key=lambda row: (row["type"], row["label"], row["id"]))
    edge_rows = sorted(valid_edges.values(), key=lambda row: (row["type"], row["source"], row["target"]))
    with (OUTPUT / "nodes.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=NODE_FIELDS)
        writer.writeheader()
        writer.writerows(node_rows)
    with (OUTPUT / "edges.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=EDGE_FIELDS)
        writer.writeheader()
        writer.writerows(edge_rows)
    with (OUTPUT / "nodes.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
        for row in node_rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (OUTPUT / "edges.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
        for row in edge_rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")

    report = {
        "sourceEntities": len(records), "nodes": len(node_rows), "edges": len(edge_rows),
        "nodesByType": dict(sorted((kind, sum(row["type"] == kind for row in node_rows))
                                    for kind in ontology["nodeTypes"])),
        "edgesByType": dict(sorted((kind, sum(row["type"] == kind for row in edge_rows))
                                    for kind in ontology["relationshipTypes"])),
    }
    (OUTPUT / "quality-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
