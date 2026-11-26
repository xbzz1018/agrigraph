# 本地运行手册

以下步骤从仓库根目录开始。后端 Python 命令使用已有的 Conda `AiJava` 环境。

以下 `C:\path\to\...` 是占位路径，运行前改为本机文件和公开数据目录的绝对路径。

## 安装依赖

准备已有的 Conda `AiJava` 环境（Python 3.10）、Node.js 22+、pnpm 9.15.9 和 Docker。首次获取代码后，从仓库根目录安装后端和前端依赖：

```powershell
Push-Location backend-python
conda run --no-capture-output -n AiJava python -m pip install -r requirements.txt
conda run --no-capture-output -n AiJava python -m pip check
Pop-Location
Push-Location frontend
pnpm install --frozen-lockfile
Pop-Location
```

只体验离线案例时，执行上方的后端依赖安装步骤，然后按[离线案例](../examples/evidence-case/README.md)运行脚本。该案例无需安装前端、启动 Docker 或配置模型。

## 配置模型

首次配置时，从仓库根目录复制模板：

```powershell
Copy-Item .env.ai.example .env.ai
```

编辑 `.env.ai`，填写文本服务的 `GATEWAY_API_BASE`、`GATEWAY_API_KEY`、`GATEWAY_MODEL`，并把 `AGRIGRAPH_DATA_ROOT` 改为本机公开数据目录。需要图片功能时，再填写 `VISION_API_BASE`、`VISION_API_KEY`、`VISION_MODEL`。已有配置时直接编辑，保留本机密钥与路径。

文本模型默认使用 DeepSeek V4 Flash，图片模型默认使用 Qwen3-VL-Flash，可通过上述变量修改服务地址与模型名称。

## 启动依赖服务

启动 Docker 后，在仓库根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev\start-acceptance-dependencies.ps1
```

Compose 启动 Elasticsearch、Neo4j、PostgreSQL 和 Redis，默认端口分别为 `29200`、`27474/27687`、`25432` 和 `26379`；不依赖其他项目容器。

脚本会生成 `var/acceptance/infra.env`，记录本机容器的连接配置。应用启动器自动加载该文件；下方 Elasticsearch 导入命令通过 `--env-file` 加载同一份配置。

## 整理并导入知识数据

按[数据清单](../config/datasets/agrigraph-datasets.json)中的来源获取公开资料。数据整理脚本读取以下文件，路径相对于 `AGRIGRAPH_DATA_ROOT`：

```text
raw/agriculture-text/tomato/tomato-disease.xlsx
raw/agriculture-text/tomato/tomato-pest.xlsx
raw/agriculture-text/rice/rice-disease.xls
raw/agriculture-text/rice/rice-pest.xls
```

将下方占位路径改为与 `.env.ai` 一致的数据目录，再整理、导入 Elasticsearch 和 Neo4j。已生成 `processed/knowledge/agriculture-entities.jsonl` 时可跳过整理步骤。

```powershell
$env:AGRIGRAPH_DATA_ROOT = 'C:\path\to\public-datasets'
powershell -ExecutionPolicy Bypass -File scripts\data\prepare-knowledge-data.ps1 -DataRoot $env:AGRIGRAPH_DATA_ROOT
Push-Location backend-python
conda run --no-capture-output -n AiJava python -m alembic upgrade head
conda run --no-capture-output -n AiJava python -m app.import_knowledge --data-root $env:AGRIGRAPH_DATA_ROOT --env-file ..\var\acceptance\infra.env
Pop-Location
powershell -ExecutionPolicy Bypass -File scripts\graph\build-neo4j-import.ps1 -DataRoot $env:AGRIGRAPH_DATA_ROOT
powershell -ExecutionPolicy Bypass -File scripts\graph\import-acceptance-neo4j.ps1 -DataRoot $env:AGRIGRAPH_DATA_ROOT
```

更多数据处理脚本见[脚本目录](../scripts/README.md)。

## 启动应用

```powershell
.\start-windows.bat
```

打开 <http://127.0.0.1:9627>，首次使用先注册账号。API 地址为 <http://127.0.0.1:8188>。未配置视觉模型时，可先使用文本问答与知识图谱。

停止应用运行 `stop-windows.bat`；停止 Docker 依赖运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev\stop-acceptance-dependencies.ps1
```

## 质量检查

```powershell
Push-Location backend-python
conda run --no-capture-output -n AiJava python -m ruff check app tests migrations
conda run --no-capture-output -n AiJava python -m pytest tests
Pop-Location
Push-Location frontend
pnpm test:request
pnpm test:sse
pnpm test:markdown
pnpm test:i18n
pnpm typecheck
pnpm build
Pop-Location
```

真实模型预检和三组评测脚本只在配置远程服务后手动执行，报告不得写入密钥、原始图片或隐藏推理。
