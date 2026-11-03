# 本地运行手册

所有 Python 命令从 `backend-python` 目录执行，并使用 `conda run --no-capture-output -n AiJava`。不在 `base` 环境安装依赖，不复制 `api.txt`，不输出 `.env.ai`。

以下 `C:\path\to\...` 是占位路径，运行前改为本机文件和公开数据目录的绝对路径。

## 配置与启动

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev\configure-from-api-txt.ps1 -ApiFile 'C:\path\to\api.txt'
powershell -ExecutionPolicy Bypass -File scripts\dev\start-acceptance-dependencies.ps1
.\start-windows.bat
```

文本模型为 DeepSeek V4 Flash；图片模型为 Qwen3-VL-Flash。视觉能力未配置时，文本问答和知识图谱仍可运行，图片入口返回未配置状态。

Compose 启动 Elasticsearch、Neo4j、PostgreSQL 和 Redis，默认端口分别为 `29200`、`27474/27687`、`25432` 和 `26379`；不依赖其他项目容器。

## 依赖和数据

```powershell
$env:AGRIGRAPH_DATA_ROOT = 'C:\path\to\public-datasets'
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
