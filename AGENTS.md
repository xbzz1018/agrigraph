# AgriGraph Evidence QA 开发约束

## 环境

- Python 只能使用现有 Conda 环境 `AiJava`（Python 3.10.19），禁止在 `base` 安装依赖或创建新环境。
- 后端命令从 `backend-python` 执行，前端命令从 `frontend` 执行。
- 不恢复 Java、Spring Boot、Maven 或旧项目端口。
- 文本、视觉、Embedding 和 Reranker 模型只调用兼容 API，不在项目脚本中下载模型。

## 架构边界

- `app/agents`：固定 LangGraph 工作流、状态、SSE 和运行审计。
- `app/integrations`：DeepSeek、Qwen3-VL、Elasticsearch、Neo4j 客户端边界。
- `app/domain`：农业查询、实体、图谱和防治输出规则。
- `app/evaluation`：可脱离服务复核的指标公式。
- `app/repositories`：SQLite 用户、会话和运行审计。
- `app/repositories/memory.py`：Redis 短期上下文、PostgreSQL 长期记忆事实和 ES 检索副本。
- `app/core/container.py`：外部客户端和服务的唯一装配位置。

Query Router 是确定性工作流节点，不是 Supervisor。Vision 只提取作物、部位和可见症状，不直接确诊；Answer 只能消费 ES/Neo4j 证据；Redis/PostgreSQL/ES 记忆只帮助理解追问，不能作为事实证据。

## 防治安全红线

- 对外只回答农业防治、生物防治和可用于防治病害的药剂/有效成分名称。
- 严禁输出剂量、浓度、倍液、亩用量、公顷用量、混配比例、施药次数和安全间隔期。
- 用户追问具体用量时只返回登记标签与农技人员提示。
- 原始公开数据只读；导入 ES/Neo4j 前抽取并清洗防治选项。

## 保密边界

- 不读取到终端或提交 `.env.ai`、API Key、数据库密码和 JWT 密钥。
- 不把原始图片、隐藏推理、完整提示词或外部网页正文写入报告。
- 不删除 `var/` 下未知运行数据库、checkpoint、上传文件或报告。
- 原 `F:\code\homework\project\2-AgriGraph` 是只读历史实现，不得 reset、恢复或覆盖。

## 质量门禁

```powershell
Push-Location backend-python
conda run --no-capture-output -n AiJava python -m ruff check app tests migrations
conda run --no-capture-output -n AiJava python -m pytest tests
conda run --no-capture-output -n AiJava python -m alembic upgrade head
Pop-Location

Push-Location frontend
pnpm typecheck
pnpm build
Pop-Location
```

核心验收只报告文本知识问答、图片症状理解和防治关系三组指标。任何模型失败、样例缺失、ES/Neo4j 降级或安全边界失败，都不能生成通过状态的候选报告。
