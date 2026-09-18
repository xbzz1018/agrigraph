"""Prepared knowledge import contract tests."""

from __future__ import annotations

import json
from types import SimpleNamespace

from app.cli.import_knowledge import _entity_document, _mapping, load_documents


def test_entity_document_preserves_evaluation_identity_and_search_text():
    document_id, source = _entity_document(
        {
            "id": "entity-1",
            "crop": "番茄",
            "name": "番茄早疫病",
            "entityType": "病害",
            "entityTypeCode": "disease",
            "summary": "主要叶部病害",
            "symptoms": "同心轮纹",
            "occurrenceFactors": "高湿",
            "source": {"license": "CC0"},
        }
    )

    assert document_id == "entity-1"
    assert source["fileMd5"] == "entity-1"
    assert source["crop"] == "番茄"
    assert "同心轮纹" in source["content"]
    assert "高湿" in source["content"]


def test_load_documents_rejects_duplicate_ids(tmp_path):
    root = tmp_path / "processed" / "knowledge"
    root.mkdir(parents=True)
    entity = {"id": "same", "name": "A"}
    (root / "agriculture-entities.jsonl").write_text(json.dumps(entity) + "\n" + json.dumps(entity) + "\n", encoding="utf-8")
    (root / "source-documents.jsonl").write_text("", encoding="utf-8")

    try:
        load_documents(tmp_path)
    except ValueError as exc:
        assert "duplicate" in str(exc)
    else:
        raise AssertionError("duplicate IDs must be rejected")


def test_mapping_uses_bm25_text_fields():
    settings = SimpleNamespace()
    properties = _mapping(settings)["mappings"]["properties"]
    assert "content" in properties
    assert "controlOptions" in properties
