"""提供农业实体、图谱浏览、数据集目录和评测所需的领域逻辑。"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from app.core.settings import Settings
from app.integrations.retrieval import Bm25Retriever

TYPE_LABELS = {
    "Crop": "作物",
    "Disease": "病害",
    "Pest": "虫害",
    "Symptom": "症状",
    "Pathogen": "病原",
    "ActiveIngredient": "有效成分",
    "BiologicalControl": "生物防治",
    "AgriculturalPractice": "农业防治",
    "PlantPart": "危害部位",
    "EnvironmentFactor": "环境条件",
    "GrowthStage": "生育期",
    "ImageCase": "图片案例",
}


class AgricultureDomain:
    """农业实体、图谱浏览、数据集与评测的应用领域服务。"""

    def __init__(self, settings: Settings, retriever: Bm25Retriever | None = None, graph_driver: Any | None = None):
        self.settings = settings
        self.retriever = retriever or Bm25Retriever(settings)
        self.graph_driver = graph_driver
        self._image_hash_index: dict[str, set[str]] | None = None

    def image_case_candidates(self, image_path: str | Path, limit: int = 3) -> list[dict[str, Any]]:
        """按公开核验图片的 SHA-256 反查已知案例，作为视觉候选先验。"""

        path = Path(image_path)
        if not path.is_file():
            return []
        if self._image_hash_index is None:
            self._image_hash_index = self._build_image_hash_index()
        digest = hashlib.sha256(path.read_bytes()).hexdigest().lower()
        entity_ids = list(self._image_hash_index.get(digest, set()))
        values: list[dict[str, Any]] = []
        for entity_id in entity_ids[: max(1, limit)]:
            try:
                entity = self.entity(entity_id)
            except LookupError:
                continue
            values.append(
                {
                    "id": entity["id"],
                    "name": entity["name"],
                    "crop": entity["crop"],
                    "category": entity["category"],
                    "categoryLabel": entity["categoryLabel"],
                    "score": 1.0,
                    "matchMethod": "IMAGE_SHA256",
                }
            )
        return values

    def _build_image_hash_index(self) -> dict[str, set[str]]:
        knowledge = self.settings.data_root / "processed" / "knowledge"
        manifest = knowledge / "image-entity-map.jsonl"
        if not manifest.is_file():
            return {}
        index: dict[str, set[str]] = defaultdict(set)
        for line in manifest.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            if str(item.get("verificationStatus", "")).upper() != "VERIFIED":
                continue
            entity_id = str(item.get("entityId") or "")
            relative = str(item.get("thumbnailFile") or "")
            if not entity_id or not relative:
                continue
            image_file = (self.settings.data_root / relative).resolve()
            if not image_file.is_relative_to(self.settings.data_root.resolve()) or not image_file.is_file():
                continue
            digest = hashlib.sha256(image_file.read_bytes()).hexdigest().lower()
            index[digest].add(entity_id)
        return dict(index)

    def datasets(self) -> list[dict[str, Any]]:
        return [
            self._dataset(
                "plant-village",
                "PlantVillage",
                "PlantVillage 作物病害图片",
                "Penn State /公开研究数据",
                "图片诊断与相似案例",
                "BASE",
                0,
                0,
            ),
            self._dataset(
                "plant-doc", "PlantDoc", "PlantDoc 田间病害图片", "公开研究数据", "真实田间图片验证", "BASE", 0, 0
            ),
            self._dataset(
                "cn-agri-knowledge",
                "China Agriculture Public Knowledge",
                "中国农业公开知识资料",
                "农业农村部门及科研院所",
                "病虫害正文与安全防治",
                "SUPPLEMENT",
                0,
                0,
            ),
            self._dataset(
                "agrigraph-curated",
                "AgriGraph Curated Graph",
                "AgriGraph 规范化图谱",
                "AgriGraph",
                "实体、关系与检索评测",
                "BASE",
                0,
                0,
            ),
        ]

    def growth_stages(self, crop: str) -> list[dict[str, Any]]:
        values = {
            "水稻": [
                ("苗期", "幼苗建立根系和叶片", "保持适宜水层，关注苗期病害"),
                ("分蘖期", "茎基部产生分蘖", "协调水肥，控制无效分蘖"),
                ("拔节孕穗期", "茎秆伸长并形成幼穗", "保障养分，监测纹枯病和螟虫"),
                ("抽穗扬花期", "稻穗抽出并完成开花", "避免高温和缺水，关注稻瘟病"),
                ("灌浆成熟期", "籽粒灌浆并逐步成熟", "保持叶片功能，适时断水收获"),
            ],
            "番茄": [
                ("育苗期", "幼苗形成真叶和健壮根系", "控制湿度，预防猝倒病"),
                ("定植缓苗期", "根系恢复并开始新叶生长", "缓苗后逐步控水促根"),
                ("开花坐果期", "花序开放并形成幼果", "协调温湿度和授粉条件"),
                ("果实膨大期", "果实快速增重", "平衡水肥，监测晚疫病和灰霉病"),
                ("转色采收期", "果实转色并达到商品成熟", "分批采收，控制裂果和病果"),
            ],
        }
        selected = values.get(crop, values["水稻"])
        return [
            {
                "id": f"{crop}-{index}",
                "name": name,
                "order": index,
                "morphology": morphology,
                "management": management,
                "risks": [],
                "images": [],
            }
            for index, (name, morphology, management) in enumerate(selected, 1)
        ]

    def list_entities(
        self, crop: str, category: str, part: str, keyword: str, image_status: str, page: int, page_size: int
    ) -> dict[str, Any]:
        filters: list[dict[str, Any]] = []
        if crop:
            filters.append({"match": {"crop": crop}})
        if category:
            filters.append({"term": {"category.keyword": category}})
        if part:
            filters.append({"match": {"affectedParts": part}})
        must = (
            [{"multi_match": {"query": keyword, "fields": ["name^3", "summary", "symptoms", "aliases"]}}]
            if keyword
            else []
        )
        query = {"bool": {"must": must, "filter": filters}}
        response = self._es_search(query, page_size, max(0, page - 1) * page_size)
        items = [self._entity(hit.get("_source", {}), str(hit.get("_id", ""))) for hit in response]
        if image_status == "WITH":
            items = [item for item in items if item["images"]]
        if image_status == "WITHOUT":
            items = [item for item in items if not item["images"]]
        return {"items": items, "total": len(items), "page": page, "pageSize": page_size}

    def entity(self, entity_id: str) -> dict[str, Any]:
        hit = self._es_get(entity_id)
        if hit is None:
            raise LookupError("未找到农业知识实体")
        return self._entity(hit, entity_id)

    def suggestions(self, query: str, crop: str, limit: int) -> list[dict[str, Any]]:
        result = self.list_entities(crop, "", "", query, "", 1, limit)
        return [self._suggestion(item) for item in result["items"]]

    def symptom_candidates(self, crop: str, symptoms: str, parts: str, limit: int) -> list[dict[str, Any]]:
        query = " ".join(value for value in [symptoms, parts] if value).strip()
        values = self.list_entities(crop, "", parts.split(",")[0] if parts else "", query, "", 1, limit)["items"]
        return [
            {
                **self._suggestion(item),
                "summary": item["summary"],
                "score": 0.5,
                "matchedSymptoms": [symptoms] if symptoms else [],
                "matchedParts": item["affectedParts"],
                "imageUrl": item["images"][0]["url"] if item["images"] else "",
            }
            for item in values
        ]

    def similar(self, entity_id: str, limit: int) -> list[dict[str, Any]]:
        source = self.entity(entity_id)
        values = self.list_entities(source["crop"], source["category"], "", source["symptoms"], "", 1, limit + 1)[
            "items"
        ]
        return [
            {
                "id": item["id"],
                "name": item["name"],
                "categoryLabel": item["categoryLabel"],
                "summary": item["summary"],
                "score": 0.5,
                "sharedSymptoms": [],
                "sharedParts": list(set(source["affectedParts"]) & set(item["affectedParts"])),
                "sharedPathogens": [],
            }
            for item in values
            if item["id"] != entity_id
        ][:limit]

    def compare(self, ids: list[str]) -> dict[str, Any]:
        items = [self.entity(item) for item in ids[:3]]
        return {
            "crop": items[0]["crop"] if items else "",
            "category": items[0]["category"] if items else "",
            "items": items,
        }

    def overview(self, crop: str) -> dict[str, Any]:
        values = self.list_entities(crop, "", "", "", "", 1, 100)["items"]
        counts = Counter(item["category"] for item in values)
        return {
            "crop": crop,
            "entityCounts": dict(counts),
            "relationCoverage": {},
            "imageCoveredEntities": sum(bool(item["images"]) for item in values),
            "verifiedImages": sum(len(item["images"]) for item in values),
            "featuredEntities": [self._suggestion(item) for item in values[:9]],
        }

    def graph(self, root_id: str, relation_types: str = "") -> dict[str, Any]:
        allowed = [item for item in relation_types.split(",") if item]
        where = "AND type(r) IN $types" if allowed else ""
        records = self._neo4j(
            f"MATCH (n)-[r]-(m) WHERE toString(coalesce(n.id, elementId(n)))=$id {where} "
            "RETURN n,r,m,type(r) AS relation LIMIT 120",
            id=root_id,
            types=allowed,
        )
        if not records:
            return self._empty_graph(root_id, "Neo4j 未连接或当前实体暂无关系")
        nodes: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, Any]] = []
        counts: Counter[str] = Counter()
        for index, record in enumerate(records):
            left, right = record["n"], record["m"]
            left_id, right_id = self._node_id(left), self._node_id(right)
            nodes[left_id], nodes[right_id] = self._node(left, left_id), self._node(right, right_id)
            relation = str(record["relation"])
            counts[relation] += 1
            edges.append(
                {
                    "id": f"{left_id}-{relation}-{right_id}-{index}",
                    "source": left_id,
                    "target": right_id,
                    "label": relation,
                    "type": relation,
                }
            )
        return {
            "nodes": list(nodes.values()),
            "edges": edges,
            "degraded": False,
            "message": "",
            "rootId": root_id,
            "availableRelationTypes": list(counts),
            "relationCounts": dict(counts),
        }

    def path(self, source_id: str, target_id: str, max_depth: int) -> dict[str, Any]:
        depth = max(1, min(max_depth, 6))
        records = self._neo4j(
            f"MATCH p=shortestPath((a)-[*..{depth}]-(b)) WHERE toString(coalesce(a.id,elementId(a)))=$source "
            "AND toString(coalesce(b.id,elementId(b)))=$target RETURN nodes(p) AS nodes, relationships(p) AS rels LIMIT 1",
            source=source_id,
            target=target_id,
        )
        if not records:
            return self._empty_graph(source_id, "未找到关系路径或 Neo4j 不可用")
        nodes = {self._node_id(node): self._node(node, self._node_id(node)) for node in records[0]["nodes"]}
        edges = []
        for index, relation in enumerate(records[0]["rels"]):
            start, end = str(relation.start_node.element_id), str(relation.end_node.element_id)
            edges.append(
                {"id": f"path-{index}", "source": start, "target": end, "label": relation.type, "type": relation.type}
            )
        return {
            "nodes": list(nodes.values()),
            "edges": edges,
            "degraded": False,
            "message": "",
            "rootId": source_id,
            "availableRelationTypes": list({edge["type"] for edge in edges}),
            "relationCounts": dict(Counter(edge["type"] for edge in edges)),
        }

    def relations(self, entity_id: str) -> list[dict[str, Any]]:
        graph = self.graph(entity_id)
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        nodes = {item["id"]: item for item in graph["nodes"]}
        for edge in graph["edges"]:
            related = edge["target"] if edge["source"] == entity_id else edge["source"]
            node = nodes.get(related)
            if node:
                groups[edge["type"]].append(
                    {
                        "id": node["id"],
                        "name": node["label"],
                        "type": node["type"],
                        "typeLabel": TYPE_LABELS.get(node["type"], node["type"]),
                    }
                )
        return [{"type": key, "label": key, "count": len(value), "entities": value} for key, value in groups.items()]

    def related_entities(self, node_id: str, crop: str, limit: int) -> list[dict[str, Any]]:
        graph = self.graph(node_id)
        return [
            {
                "id": node["id"],
                "name": node["label"],
                "crop": crop,
                "type": node["type"],
                "typeLabel": TYPE_LABELS.get(node["type"], node["type"]),
            }
            for node in graph["nodes"]
            if node["id"] != node_id and node["type"] in {"Disease", "Pest"}
        ][:limit]

    def search(self, query: str, top_k: int) -> list[dict[str, Any]]:
        hits = self.retriever.search(query, "AUTO", top_k)
        return [
            {
                "id": hit.get("_id"),
                "score": hit.get("_score", 0),
                "retrieval": hit.get("_retrieval", {}),
                **hit.get("_source", {}),
            }
            for hit in hits
        ]

    def evaluation_retrieve(self, query: str, crop: str, limit: int) -> list[dict[str, Any]]:
        return self._evaluation_values(self.retriever.search(query, crop, min(max(1, limit), 50)))

    def evaluation_control_relations(self, disease_ids: list[str]) -> list[dict[str, Any]]:
        """返回 ES 防治选项与 Neo4j 显式防治关系，供冻结评测交叉核验。"""

        values: list[dict[str, Any]] = []
        for disease_id in list(dict.fromkeys(disease_ids))[:100]:
            try:
                entity = self.entity(disease_id)
            except LookupError:
                values.append({"diseaseId": disease_id, "controlOptions": [], "graphRelations": []})
                continue
            records = self._neo4j(
                "MATCH (source)-[r:CONTROLS|PREVENTS]->(d {id:$id}) "
                "RETURN source.id AS sourceId, coalesce(source.label,source.entityName,source.id) AS source, "
                "type(r) AS relation, d.id AS targetId, coalesce(d.label,d.entityName,d.id) AS target, "
                "coalesce(r.evidence,'') AS evidence ORDER BY relation,source",
                id=disease_id,
            )
            values.append(
                {
                    "diseaseId": disease_id,
                    "diseaseName": entity["name"],
                    "controlOptions": entity.get("controlOptions", []),
                    "graphRelations": [
                        {
                            "sourceId": str(record.get("sourceId") or ""),
                            "source": str(record.get("source") or ""),
                            "relation": str(record.get("relation") or ""),
                            "targetId": str(record.get("targetId") or ""),
                            "target": str(record.get("target") or ""),
                            "evidence": str(record.get("evidence") or ""),
                        }
                        for record in records
                    ],
                }
            )
        return values

    @staticmethod
    def _evaluation_values(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
        values = []
        for hit in hits:
            source = hit.get("_source", {})
            retrieval = hit.get("_retrieval", {})
            values.append(
                {
                    "fileMd5": str(source.get("fileMd5") or source.get("file_md5") or hit.get("_id") or ""),
                    "chunkId": str(source.get("chunkId") or source.get("chunk_id") or hit.get("_id") or ""),
                    "content": str(source.get("content") or source.get("summary") or ""),
                    "score": float(hit.get("_score") or 0),
                    "datasetId": str(source.get("datasetId") or source.get("dataset_id") or ""),
                    "doi": str(source.get("doi") or ""),
                    "retrievalMode": "bm25",
                    "degraded": bool(retrieval.get("degraded", False)),
                    "degradationReason": str(retrieval.get("reason") or ""),
                    "rank": int(retrieval.get("rank") or 0),
                }
            )
        return values

    def dataset_source(self, dataset_id: str) -> dict[str, Any]:
        dataset = next((item for item in self.datasets() if item["id"] == dataset_id), None)
        if dataset is None:
            raise ValueError(f"未找到数据集: {dataset_id}")
        source = (self.settings.data_root / dataset_id).resolve()
        if not source.is_relative_to(self.settings.data_root.resolve()):
            raise ValueError("数据集路径越界")
        if not source.is_dir():
            return {"available": False, "sourceDirectory": str(source), "fileCount": 0, "totalBytes": 0}
        files = [path for path in source.rglob("*") if path.is_file()]
        return {
            "available": True,
            "sourceDirectory": str(source),
            "fileCount": len(files),
            "totalBytes": sum(path.stat().st_size for path in files),
        }

    def image_object_key(self, image_id: str) -> str:
        records = self._neo4j(
            "MATCH (n:Entity {id:$id, type:'ImageCase'}) "
            "RETURN coalesce(n.thumbnailObjectKey,n.imageObjectKey,'') AS objectKey LIMIT 1",
            id=image_id,
        )
        return str(records[0]["objectKey"]) if records else ""

    def similar_images(self, candidate_names: list[str], limit: int = 8) -> list[dict[str, Any]]:
        names = [str(name).strip().lower()[:120] for name in candidate_names if str(name).strip()][:5]
        if not names:
            return []
        records = self._neo4j(
            "MATCH (n:Entity {type:'ImageCase'}) "
            "WHERE any(term IN $names WHERE toLower(coalesce(n.entityName,'')) CONTAINS term "
            "OR toLower(coalesce(n.label,'')) CONTAINS term "
            "OR toLower(coalesce(n.summary,'')) CONTAINS term) "
            "RETURN n.id AS id, coalesce(n.entityName,n.label,'相似案例') AS name, "
            "n.sourceDatasetId AS sourceDatasetId LIMIT $limit",
            names=names,
            limit=min(max(1, limit), 8),
        )
        return [
            {
                "id": str(record["id"]),
                "name": str(record["name"]),
                "url": f"/api/v1/media/images/{record['id']}",
                "sourceDatasetId": str(record.get("sourceDatasetId") or ""),
            }
            for record in records
        ]

    def _es_search(self, query: dict[str, Any], size: int, offset: int = 0) -> list[dict[str, Any]]:
        return self.retriever.raw_search(query, min(size, 100), offset)

    def _es_get(self, entity_id: str) -> dict[str, Any] | None:
        hits = self._es_search(
            {
                "bool": {
                    "should": [
                        {"term": {"id": entity_id}},
                        {"term": {"fileMd5": entity_id}},
                        {"term": {"entityId.keyword": entity_id}},
                    ],
                    "minimum_should_match": 1,
                }
            },
            1,
        )
        if hits:
            return hits[0].get("_source", {})
        return None

    def _neo4j(self, query: str, **parameters: Any) -> list[Any]:
        try:
            if self.graph_driver is None:
                from neo4j import GraphDatabase

                auth = (
                    (self.settings.neo4j_username, self.settings.neo4j_password)
                    if self.settings.neo4j_password
                    else None
                )
                self.graph_driver = GraphDatabase.driver(
                    self.settings.neo4j_url,
                    auth=auth,
                    connection_timeout=3,
                    max_transaction_retry_time=0,
                )
            return list(self.graph_driver.execute_query(query, parameters_=parameters).records)
        except Exception:
            return []

    @staticmethod
    def _entity(source: dict[str, Any], fallback_id: str) -> dict[str, Any]:
        category = str(source.get("category") or source.get("type") or "Disease")
        images = source.get("images") if isinstance(source.get("images"), list) else []
        return {
            "id": str(source.get("id") or source.get("entityId") or fallback_id),
            "name": str(source.get("name") or source.get("title") or "未命名实体"),
            "crop": str(source.get("crop") or ""),
            "category": category,
            "categoryLabel": TYPE_LABELS.get(category, category),
            "summary": str(source.get("summary") or source.get("description") or ""),
            "symptoms": str(source.get("symptoms") or ""),
            "pathogen": str(source.get("pathogen") or ""),
            "occurrenceFactors": str(source.get("occurrenceFactors") or source.get("conditions") or ""),
            "controlOptions": source.get("controlOptions") if isinstance(source.get("controlOptions"), list) else [],
            "affectedParts": source.get("affectedParts") if isinstance(source.get("affectedParts"), list) else [],
            "aliases": source.get("aliases") if isinstance(source.get("aliases"), list) else [],
            "images": images,
            "doi": str(source.get("doi") or ""),
            "sourceDatasetId": str(source.get("sourceDatasetId") or ""),
        }

    @staticmethod
    def _suggestion(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": item["id"],
            "name": item["name"],
            "crop": item["crop"],
            "type": item["category"],
            "category": item["category"],
            "typeLabel": item["categoryLabel"],
            "categoryLabel": item["categoryLabel"],
        }

    @staticmethod
    def _node_id(node: Any) -> str:
        return str(node.get("id") or node.get("entityId") or node.element_id)

    @staticmethod
    def _node(node: Any, node_id: str) -> dict[str, Any]:
        labels = list(node.labels)
        node_type = labels[0] if labels else str(node.get("type") or "Entity")
        properties = dict(node)
        return {
            "id": node_id,
            "label": str(node.get("name") or node.get("title") or node_id),
            "type": node_type,
            "imageUrl": node.get("imageUrl"),
            "properties": properties,
        }

    @staticmethod
    def _empty_graph(root_id: str, message: str) -> dict[str, Any]:
        return {
            "nodes": [],
            "edges": [],
            "degraded": True,
            "message": message,
            "rootId": root_id,
            "availableRelationTypes": [],
            "relationCounts": {},
        }

    @staticmethod
    def _dataset(
        dataset_id: str,
        title: str,
        chinese_title: str,
        publisher: str,
        purpose: str,
        category: str,
        size: int,
        contribution: int,
    ) -> dict[str, Any]:
        return {
            "id": dataset_id,
            "title": title,
            "chineseTitle": chinese_title,
            "publisher": publisher,
            "purpose": purpose,
            "doi": "",
            "detailUrl": "",
            "sizeBytes": size,
            "license": "按原数据集许可",
            "status": "REGISTERED",
            "targetDirectory": "",
            "category": category,
            "importedCount": 0,
            "graphContribution": contribution,
            "qualityStatus": "待导入校验",
        }
