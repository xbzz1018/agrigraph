"""集中读取 AgriGraph 核心配置，忽略已退出主线的旧环境变量。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


def _first_nonempty(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip():
            return value.strip()
    return default


def _es_url() -> str:
    explicit = _first_nonempty("AGRIGRAPH_ES_URL")
    if explicit:
        return explicit
    scheme = _first_nonempty("PAISMART_ES_SCHEME", default="http")
    host = _first_nonempty("PAISMART_ES_HOST", default="127.0.0.1")
    port = _first_nonempty("PAISMART_ES_PORT", default="9200")
    return f"{scheme}://{host}:{port}"


@dataclass(frozen=True, slots=True)
class Settings:
    """番茄/水稻病虫害知识服务所需的最小只读配置。"""

    host: str
    port: int
    db_path: Path
    checkpoint_db_path: Path
    auth_required: bool
    jwt_secret: str
    gateway_api_base: str
    gateway_api_key: str
    gateway_model: str
    gateway_input_cost_per_million: float
    gateway_output_cost_per_million: float
    es_url: str
    es_index: str
    es_username: str
    es_password: str
    neo4j_url: str
    neo4j_username: str
    neo4j_password: str
    max_model_calls: int
    max_tool_calls: int
    run_timeout_seconds: int
    model_timeout_seconds: int
    bootstrap_admin_username: str
    bootstrap_admin_password: str
    data_root: Path
    vision_api_base: str
    vision_api_key: str
    vision_model: str
    vision_timeout_seconds: int
    embedding_api_base: str
    embedding_api_key: str
    embedding_model: str
    embedding_dimensions: int
    embedding_timeout_seconds: int
    reranker_api_base: str
    reranker_api_key: str
    reranker_model: str
    reranker_timeout_seconds: int
    reranker_candidate_limit: int
    redis_url: str
    short_memory_ttl_seconds: int
    short_memory_limit: int
    postgres_dsn: str
    memory_project_scope: str
    memory_index: str
    memory_ttl_days: int

    @classmethod
    def from_env(cls) -> "Settings":
        root = Path(__file__).resolve().parents[3]

        def path(name: str, default: str) -> Path:
            raw = Path(os.getenv(name, default))
            return raw if raw.is_absolute() else (root / raw).resolve()

        return cls(
            host=os.getenv("AGRIGRAPH_HOST", "127.0.0.1"),
            port=int(os.getenv("AGRIGRAPH_PORT", "8188")),
            db_path=path("AGRIGRAPH_DB_PATH", "var/agrigraph.db"),
            checkpoint_db_path=path("AGRIGRAPH_CHECKPOINT_DB_PATH", "var/langgraph-checkpoints.db"),
            auth_required=_bool("AGRIGRAPH_AUTH_REQUIRED", True),
            jwt_secret=os.getenv("PAISMART_JWT_SECRET", ""),
            gateway_api_base=_first_nonempty(
                "DEEPSEEK_API_BASE", "GATEWAY_API_BASE", default="https://api.example.invalid/v1"
            ),
            gateway_api_key=_first_nonempty("DEEPSEEK_API_KEY", "GATEWAY_API_KEY"),
            gateway_model=_first_nonempty("DEEPSEEK_MODEL", "GATEWAY_MODEL", default="deepseek-v4-flash"),
            gateway_input_cost_per_million=max(
                0.0, float(os.getenv("AGRIGRAPH_GATEWAY_INPUT_COST_PER_MILLION", "0") or "0")
            ),
            gateway_output_cost_per_million=max(
                0.0, float(os.getenv("AGRIGRAPH_GATEWAY_OUTPUT_COST_PER_MILLION", "0") or "0")
            ),
            es_url=_es_url(),
            es_index=os.getenv("AGRIGRAPH_ES_INDEX", "agrigraph_evidence_v2"),
            es_username=_first_nonempty("AGRIGRAPH_ES_USERNAME", "PAISMART_ES_USERNAME"),
            es_password=_first_nonempty("AGRIGRAPH_ES_PASSWORD", "PAISMART_ES_PASSWORD"),
            neo4j_url=_first_nonempty("AGRIGRAPH_NEO4J_URL", "NEO4J_URI", default="bolt://127.0.0.1:7687"),
            neo4j_username=_first_nonempty("AGRIGRAPH_NEO4J_USERNAME", "NEO4J_USERNAME", default="neo4j"),
            neo4j_password=_first_nonempty("AGRIGRAPH_NEO4J_PASSWORD", "NEO4J_PASSWORD"),
            max_model_calls=max(1, int(os.getenv("AGRIGRAPH_MAX_MODEL_CALLS", "4"))),
            max_tool_calls=max(1, int(os.getenv("AGRIGRAPH_MAX_TOOL_CALLS", "8"))),
            run_timeout_seconds=max(30, int(os.getenv("AGRIGRAPH_RUN_TIMEOUT_SECONDS", "300"))),
            model_timeout_seconds=max(10, int(os.getenv("AGRIGRAPH_MODEL_TIMEOUT_SECONDS", "90"))),
            bootstrap_admin_username=_first_nonempty(
                "AGRIGRAPH_BOOTSTRAP_ADMIN_USERNAME", "PAISMART_ADMIN_USERNAME"
            ),
            bootstrap_admin_password=_first_nonempty(
                "AGRIGRAPH_BOOTSTRAP_ADMIN_PASSWORD", "PAISMART_ADMIN_PASSWORD"
            ),
            data_root=path("AGRIGRAPH_DATA_ROOT", "var/datasets"),
            vision_api_base=_first_nonempty("VISION_API_BASE"),
            vision_api_key=_first_nonempty("VISION_API_KEY"),
            vision_model=_first_nonempty("VISION_MODEL", default="qwen3-vl-flash"),
            vision_timeout_seconds=max(10, int(os.getenv("VISION_TIMEOUT", "120"))),
            embedding_api_base=_first_nonempty("AGRIGRAPH_EMBEDDING_API_BASE", "EMBEDDING_API_BASE"),
            embedding_api_key=_first_nonempty("AGRIGRAPH_EMBEDDING_API_KEY", "EMBEDDING_API_KEY"),
            embedding_model=_first_nonempty(
                "AGRIGRAPH_EMBEDDING_MODEL", "EMBEDDING_MODEL", default="BAAI/bge-m3"
            ),
            embedding_dimensions=max(1, int(os.getenv("AGRIGRAPH_EMBEDDING_DIMENSIONS", "1024"))),
            embedding_timeout_seconds=max(
                5, int(os.getenv("AGRIGRAPH_EMBEDDING_TIMEOUT_SECONDS", "30"))
            ),
            reranker_api_base=_first_nonempty("AGRIGRAPH_RERANKER_API_BASE", "RERANKER_API_BASE"),
            reranker_api_key=_first_nonempty("AGRIGRAPH_RERANKER_API_KEY", "RERANKER_API_KEY"),
            reranker_model=_first_nonempty(
                "AGRIGRAPH_RERANKER_MODEL", "RERANKER_MODEL", default="BAAI/bge-reranker-v2-m3"
            ),
            reranker_timeout_seconds=max(
                5, int(os.getenv("AGRIGRAPH_RERANKER_TIMEOUT_SECONDS", "30"))
            ),
            reranker_candidate_limit=min(
                100, max(10, int(os.getenv("AGRIGRAPH_RERANKER_CANDIDATE_LIMIT", "30")))
            ),
            redis_url=_first_nonempty("AGRIGRAPH_REDIS_URL"),
            short_memory_ttl_seconds=max(
                60, int(os.getenv("AGRIGRAPH_SHORT_MEMORY_TTL_SECONDS", "86400"))
            ),
            short_memory_limit=min(50, max(2, int(os.getenv("AGRIGRAPH_SHORT_MEMORY_LIMIT", "12")))),
            postgres_dsn=_first_nonempty("AGRIGRAPH_POSTGRES_DSN"),
            memory_project_scope=_first_nonempty(
                "AGRIGRAPH_MEMORY_PROJECT_SCOPE", default="agrigraph"
            ),
            memory_index=_first_nonempty("AGRIGRAPH_MEMORY_INDEX", default="agrigraph_memory_v1"),
            memory_ttl_days=max(1, int(os.getenv("AGRIGRAPH_MEMORY_TTL_DAYS", "365"))),
        )
