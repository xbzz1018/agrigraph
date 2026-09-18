from fastapi.testclient import TestClient

from app.main import create_app


def test_health_and_graph_rag_contract(settings):
    with TestClient(create_app(settings)) as client:
        health = client.get("/api/v1/health").json()["data"]
        assert health["workflowMode"] == "DETERMINISTIC_MULTIMODAL_KNOWLEDGE"
        assert health["retrievalMode"] == "bm25"
        assert client.get("/api/v1/knowledge-growth/tasks").status_code == 404
