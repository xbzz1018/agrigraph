# 本地运行手册

所有 Python 命令从 `backend-python` 目录执行，并使用 `conda run --no-capture-output -n AiJava`。不在 `base` 环境安装依赖，不把 Provider 配置、Key 或 `.env.ai` 写入 Git。

## 配置与启动

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev\configure-from-api-txt.ps1 -ApiFile 'C:\path\to\provider-config.txt'
powershell -ExecutionPolicy Bypass -File scripts\dev\start-acceptance-dependencies.ps1
.\start-windows.bat
```

文本和视觉模型由本地 Provider 配置决定。视觉能力未配置时，文本问答和知识图谱仍可运行，图片入口返回未配置状态。

Compose 只包含 Elasticsearch 和 Neo4j，端口为 `29200`、`27474/27687`；不依赖 MinIO、Redis 或其他项目容器。

## 依赖和数据

```powershell
Push-Location backend-python
conda run --no-capture-output -n AiJava python -m alembic upgrade head
conda run --no-capture-output -n AiJava python -m app.import_knowledge --data-root $env:AGRIGRAPH_DATA_ROOT
Pop-Location
```

## 质量检查

```powershell
Push-Location backend-python
conda run --no-capture-output -n AiJava python -m ruff check app tests migrations
conda run --no-capture-output -n AiJava python -m pytest tests
Pop-Location
Push-Location frontend
pnpm typecheck
pnpm build
Pop-Location
```

真实模型预检和三组评测脚本只在配置远程服务后手动执行，报告不得写入密钥、原始图片或隐藏推理。
