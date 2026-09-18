# 系统架构

```text
Redis 短期上下文 + PostgreSQL/ES 长期记忆（非证据）
                         ↓
文本 -> DeepSeek AgricultureQuery -\
                                  -> ES BM25 -> 可选 BGE 重排 -> Neo4j 关系 -> DeepSeek Answer
图片 -> Qwen3-VL VisionObservation /
                                                                       ↓
                                                     Evidence Check -> Output Boundary
```

LangGraph 只编排固定节点：`session_context`、`query_router`、`document_research`、`graph_reasoning`、`answer`、`evidence_check`、`output_boundary`。没有 LLM Supervisor，也没有 Agent 自主协商。

- 文档研究节点调用 Elasticsearch BM25；仅症状和发生条件问题在配置可用时执行 BGE-Reranker。
- 图谱研究节点只能调用 Neo4j，重点关系为 `HAS_SYMPTOM`、`CAUSED_BY`、`FAVORED_BY`、`CONTROLS`、`PREVENTS`。
- Answer 节点不能调用检索工具，只消费文档和图谱证据。
- Redis 短期上下文与 PostgreSQL/ES 长期记忆仅帮助理解追问，不进入 Claim、引用或 grounded 判定。
- Vision 只提取图片中的作物、部位、可见症状和质量提示，不直接确诊。

## 防治信息边界

导入阶段从公开原文抽取别名归一化后的药剂/有效成分，并剔除原始使用参数。回答阶段再次过滤百分比、倍液、亩用量、混配、次数和安全间隔表达。用户追问剂量时只返回登记标签与农技人员提示。

## 组件职责

| 组件 | 职责 |
|---|---|
| FastAPI | 鉴权、问答、图片、知识库、图谱和运行接口 |
| LangGraph | 固定工作流、Checkpoint、SSE 事件 |
| Elasticsearch | BM25 候选检索与长期记忆向量副本 |
| BGE-M3 / Reranker | 长期记忆向量化与症状候选重排 |
| Neo4j | 病害关系组织与路径解释 |
| SQLite | 用户、会话和运行审计 |
| PostgreSQL | 用户农业档案、记忆版本和冲突记录 |
| Redis | 带 TTL 的会话短期上下文 |
| Vue 3 | 面向种植户和科研/农技人员的统一结果界面 |
