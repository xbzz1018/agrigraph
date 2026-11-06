# AgriGraph Evidence QA

面向番茄与水稻病虫害的多模态知识问答：从文字或图片症状查找候选知识，用图谱补充关系，再生成带引用的回答。

[项目案例](docs/project-case.md) · [离线运行结果](examples/evidence-case/result.json) · [本地启动](docs/runbook.md) · [验证与限制](docs/acceptance/public-verification.md)

## 一次问答如何完成

```mermaid
flowchart LR
    A[文字或图片症状] --> B[结构化查询]
    B --> C[BM25 候选与条件重排]
    C --> D[Neo4j 关系证据]
    D --> E[回答与 Claim 引用核验]
    E --> F[防治信息边界检查]
```

- 文字和图片共用知识链路；视觉模型只提取作物、部位与可见症状。
- Elasticsearch 召回候选，症状与发生条件问题可使用外部 Reranker；Neo4j 补充症状、病原、发生条件和防治关系。
- 回答中的 Claim 关联证据 ID；缺少支持的陈述会被移除。该检查使用确定性规则，仍需要人工复核。
- SSE 与最终结果报告实际检索模式和重排降级原因；会话记忆帮助理解追问，不作为事实依据。

## 不配置模型也能检查的案例

```powershell
conda run --no-capture-output -n AiJava python scripts/demo/run-evidence-case.py
```

案例使用合成症状、候选资料和离线服务替身，实际执行本仓库的 LangGraph、工具封装、引用核验和 SSE 转换。它覆盖 BM25、重排成功、重排失败、重排空结果和无证据五条路径，不连接数据库服务或付费模型。

完整输入、运行结果及源码摘要见 [examples/evidence-case](examples/evidence-case/README.md)。真实模型与真实知识库的验收另见[验证记录](docs/acceptance/public-verification.md)。

## 启动真实服务

需要已有 Conda `AiJava`（Python 3.10）、Node.js、pnpm 和 Docker。前端依赖要求 Node.js 18.20+，CI 使用 Node.js 20 / pnpm 9.15.9。使用外部兼容 API 配置文本、视觉和可选重排能力。

```powershell
# 先按运行手册配置本机模型与公开数据路径
powershell -ExecutionPolicy Bypass -File scripts/dev/start-acceptance-dependencies.ps1
.\start-windows.bat
```

前端 `http://127.0.0.1:9627`，API `http://127.0.0.1:8188`。依赖包括 Elasticsearch、Neo4j、PostgreSQL 和 Redis；用户与运行审计使用 SQLite。安装、数据导入、模型配置和检查命令见[运行手册](docs/runbook.md)。

## 验证状态

| 材料 | 能说明什么 |
| --- | --- |
| 后端回归、前端类型检查与构建 | 工作流规则、接口契约与构建可检查 |
| 五条离线案例 | 证据传递、无来源陈述过滤、检索模式与降级行为 |
| [历史候选摘要](docs/acceptance/historical-candidate.json) | 本地旧快照的文本、图片、防治三组记录；无 Git commit，不代表当前版本成绩 |

真实模型、完整数据栈与当前源码的联合验收仍需单独执行。历史图片症状覆盖率为 12.78%，保留为已知弱项；不将候选召回率等同于诊断准确率。

## 继续阅读

| 想了解什么 | 入口 |
| --- | --- |
| 业务问题、个人工作与工程取舍 | [项目案例](docs/project-case.md) |
| 组件职责、记忆与证据边界 | [系统架构](docs/architecture.md) |
| 数据划分、指标与失败条件 | [评测说明](docs/evaluation/rag-evaluation.md) |
| 检索契约及已解决的问题 | [问题与修复](docs/acceptance/issues-and-fixes.md) |

本项目使用公开资料独立完成脱敏工程实现，不包含客户或内部数据。图片只提供症状观察和候选解释；涉及农药用量、浓度、混配、频次等具体用法时，返回登记标签与农技人员提示。
