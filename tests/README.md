# 跨服务测试与固定样本

本目录只保存不属于某个 Python 模块的评测样本。当前农业 RAG V2 包含：

- `evaluation/agriculture-rag-dev.jsonl`：40 条，仅用于参数和路由分析。
- `evaluation/agriculture-rag-test-v2.jsonl`：160 条冻结验收集，其中 40 条显式标记为生成评测。
- `evaluation/agriculture-rag-stability.jsonl`：20 条稳定性集，每条执行 3 次。

后端单元和 API 测试位于 `backend-python/tests/`，已按 `api/`、`agents/`、`integrations/`、`core/`、`cli/` 分类。评测方法见 [`../docs/evaluation/rag-evaluation.md`](../docs/evaluation/rag-evaluation.md)。
