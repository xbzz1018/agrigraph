# 公开验证记录与限制

本次整理日期：2026-11-05。[返回首页](../../README.md) · [项目案例](../project-case.md)

## 当前代码的确定性验证

审阅起点是 PR #27 的提交 `9ebb019092c58368aea7c7c8e92d133aff6b1bbf`。该提交的 GitHub 后端、前端和 CodeQL 检查通过；新增离线案例随本 PR 重新执行质量门禁。

2026-11-05 本机复核：44 项后端测试、Ruff、前端类型检查和专用临时 SQLite 的 Alembic 迁移通过。完整数据栈及真实模型未在本次启动；前端构建与新提交的 Linux 检查以对应 PR 检查结果为准。

```powershell
Push-Location backend-python
conda run --no-capture-output -n AiJava python -m ruff check app tests migrations ../scripts/demo
conda run --no-capture-output -n AiJava python -m pytest tests
Pop-Location
Push-Location frontend
pnpm typecheck
pnpm build
Pop-Location
```

检索契约测试覆盖配置开关、重排成功、HTTP 失败、空结果、原因码脱敏、SSE/最终结果一致性和 OpenAPI。新增五条完整工作流案例检查证据 ID 传递、无来源陈述过滤与无证据回答。生成的 [result.json](../../examples/evidence-case/result.json) 使用合成数据，并附关键源码文本摘要，不代表真实模型评测。

`/api/v1/health` 的 `retrievalMode` 是配置策略（`bm25` / `bm25_conditional_rerank`），`rerankerConfigured` 只代表配置存在。每次结果的 `retrieval` 才描述实际取到证据的路径；无文档证据时返回 `none`，不能据此推断 Elasticsearch 是否健康。

## 历史候选记录

[historical-candidate.json](historical-candidate.json) 从本地历史摘要按白名单抽取，保留原始工件 SHA-256、数据/源码/工作流摘要、模型标识、样本数与完整三组指标，不包含原始图片、逐样例回答、外部原文或凭据。

原记录为 `COMPLETED_CANDIDATE / CANDIDATE_NOT_FORMAL_RELEASE`，源码状态为 `UNVERSIONED_LOCAL`，没有 Git commit 和执行日期。这里只公开它实际记录的结果，未重新审核原始逐样例、图片授权或指标实现，不能证明当前公开仓库版本达到同样水平。

| 指标组 | 样本口径 | 原摘要记录 |
| --- | --- | --- |
| 文本检索 | 共 160 条，召回指标统计 144 条正例 | Recall@10 0.9514；MRR 0.8217；nDCG@10 0.8533 |
| 回答生成 | 40 条：32 正例、8 负例 | Claim Coverage 0.8229；Citation Coverage 0.9062；Citation Correctness 0.8906；Negative Refusal 0.875 |
| 图片症状 | 30 张 | 结构化成功率 1.0；症状覆盖率 0.1278；候选 Recall@3 1.0 |
| 防治关系 | 30 条 | Recall@5 1.0；关系正确率 1.0；用法泄漏率 0.0 |

图片症状覆盖率偏低，且历史样本量有限。较高候选召回率不能单独证明症状识别完整或现场诊断准确。

## 尚未由本次验证证明

- 当前公开源码与 Elasticsearch、Neo4j、PostgreSQL、Redis、真实文本/视觉/Reranker 服务的联合验收。
- 更换模型后的质量、成本、延迟和失败率；历史摘要不能代替重新执行。
- 图片现场诊断能力或确定性引用规则对所有事实错误的识别能力。

完整验收按[运行手册](../runbook.md)和[评测说明](../evaluation/rag-evaluation.md)执行。Dev 调参后冻结配置，再跑独立 Test；模型失败、样例缺失、依赖降级或输出边界失败必须保留并报告。
