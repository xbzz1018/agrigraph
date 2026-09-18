# Python 后端

本目录包含 AgriGraph 唯一主后端：FastAPI API、固定 LangGraph 工作流、BM25/Neo4j 检索、SQLite 仓储、Alembic 和测试。

- 启动入口：`app/main.py`，运行 `conda run --no-capture-output -n AiJava python -m uvicorn app.main:app --host 127.0.0.1 --port 8188`
- 数据迁移：`conda run -n AiJava python -m alembic upgrade head`
- 知识导入：`conda run --no-capture-output -n AiJava python -m app.import_knowledge --data-root $env:AGRIGRAPH_DATA_ROOT`
- 数据库结构：`migrations/`
- 测试：`tests/`

所有 Python 命令使用 Conda `AiJava`。分层与调用链见 [`../docs/architecture.md`](../docs/architecture.md)，完整运行步骤见 [`../docs/runbook.md`](../docs/runbook.md)。
