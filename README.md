# AgriGraph Evidence QA

面向番茄和水稻病虫害的多模态知识服务系统，重点演示 GraphRAG、证据约束、图片症状观察和安全边界如何组合成可审计的 Agent 应用。

这是一个使用公开资料独立完成的脱敏工程化项目，不包含原项目源码、内部数据、客户资料或未公开文档。系统只提供辅助知识服务，不替代现场调查、农技人员诊断或农药登记标签。

## 项目定位

AgriGraph 解决的不是“让模型直接猜病害”，而是把农业问题拆成可检查的观察、检索、图谱解释和引用回答：

1. 文本或图片先转换为结构化农业查询和可见症状。
2. Elasticsearch 找到候选知识，Neo4j 补充实体关系和解释路径。
3. Answer Agent 只能消费已检索证据，Evidence/Safety 规则负责引用和输出边界。
4. 每次运行保留步骤、工具、Token、延迟和评测信息，便于复盘失败。

## 核心链路

~~~text
农业问题
  → Redis 短期上下文 + PostgreSQL/ES 长期记忆
  → 确定性 Query Router
  → Elasticsearch BM25 + 可选 BGE 重排 + Neo4j 图谱检索
  → Answer Agent 生成回答
  → Evidence Agent 核验引用
  → Safety Agent 安全审查
  → SSE 返回答案与运行轨迹
~~~

系统的重点是症状理解、病虫害候选检索和图谱解释，不是增加 Agent 数量。会话上下文只帮助理解多轮追问，不能作为事实依据。

## 功能

- 农业知识问答与 SSE 流式输出。
- Elasticsearch BM25 候选检索与 Neo4j 关系解释。
- 症状/条件问题的可选 BGE-Reranker 二阶段重排。
- Redis 短期上下文与 PostgreSQL/Elasticsearch 长期记忆检索。
- Neo4j 实体、关系和路径查询。
- 图片辅助诊断：视觉观察转成农业查询，再复用 GraphRAG。
- Run、Step、工具轨迹、Token 和延迟审计。
- 文本、图片症状和防治关系三组评测。

## 环境

- Conda AiJava，Python 3.10.19。
- Node.js 18.20+，pnpm 8.7+。
- Docker Desktop。
- 公开数据目录：通过 `AGRIGRAPH_DATA_ROOT` 指向本机的公开数据目录。

所有 Python 命令必须通过 conda run -n AiJava 执行。启动脚本会检查解释器路径，直接使用 base 环境会失败。

## 配置新模型

不要把 `api.txt` 复制到项目。使用本地配置脚本从指定文件生成被忽略的 `.env.ai`：

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\dev\configure-from-api-txt.ps1 `
  -ApiFile 'C:\Users\xzheng\Desktop\api.txt'
~~~

配置映射：

- DeepSeek V4 Flash：问题结构化与回答生成。
- 阿里 Workspace qwen3-vl-flash：图片症状提取，可按需配置。

配置完成后可运行知识数据 dry-run（只输出数量和检索模式，不输出密钥）：

~~~powershell
Push-Location backend-python
conda run -n AiJava python -m app.import_knowledge --data-root $env:AGRIGRAPH_DATA_ROOT --dry-run
Pop-Location
~~~

脚本只输出配置生成结果，不输出密钥。`.env.ai`、数据库、图片和运行报告均不进入交付目录。

## 启动

~~~powershell
powershell -ExecutionPolicy Bypass -File scripts\dev\start-acceptance-dependencies.ps1
.\start-windows.bat
~~~

访问：

- 前端：http://127.0.0.1:9627
- API：http://127.0.0.1:8188
- 健康检查：http://127.0.0.1:8188/api/v1/health/dependencies

Docker 依赖使用独立端口：Elasticsearch 29200、Neo4j 27474/27687、PostgreSQL 25432、Redis 26379，不启动对象存储。

## 数据导入与评测

~~~powershell
Push-Location backend-python
conda run -n AiJava python -m alembic upgrade head
conda run -n AiJava python -m app.import_knowledge --data-root $env:AGRIGRAPH_DATA_ROOT --env-file ..\var\acceptance\infra.env
Pop-Location
~~~

完整验收：

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\dev\run-automated-acceptance.ps1 `
  -DataRoot $env:AGRIGRAPH_DATA_ROOT `
  -RequestTimeoutSeconds 900
~~~

评测报告绑定数据、模型、Prompt、工具 Schema、工作流和评测器哈希。模型更换后必须重新建索引和重跑评测，不能复用旧项目指标。

当前本地候选验收状态为 `COMPLETED_CANDIDATE`；原始逐样例和摘要位于被忽略的 `var/reports/`，不作为正式 Git 发布报告。

## 目录

~~~text
backend-python/   FastAPI、LangGraph、GraphRAG、分层记忆、仓储和测试
frontend/         Vue 3 问答、知识库、图谱、诊断和运行页面
config/           公开配置、本体和 Prompt
scripts/          Docker、数据准备、ES/Neo4j 导入和验收
tests/evaluation/ 冻结评测样本
docs/             架构、复现、运维和验收说明
~~~

## 安全边界

图片诊断只输出候选观察，不替代现场诊断。涉及农药剂量、浓度、倍液、混配、施药次数或安全间隔期时，只返回登记标签与农技人员提示，不生成具体用法。

本仓库是独立的精简展示版。完整历史实现不作为本仓库的运行时依赖，也不应把本地原始数据目录、数据库、图片或运行报告提交进来。

## 适合展示的能力

- 固定 LangGraph 工作流，而不是用“多 Agent”掩盖没有边界的自由编排。
- 文本检索、图谱路径和视觉观察之间的证据传递。
- SSE 运行轨迹、引用核验、成本/延迟记录和冻结评测集。
- 对农业防治内容的安全过滤和人工确认边界。
