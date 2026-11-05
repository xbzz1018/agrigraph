# 离线证据案例

这是可运行的工程演示，输入资料为人工编写的合成 Fixture，不是农业知识库内容或真实病害诊断。

- [fixture.json](fixture.json)：症状问题、两个合成候选和一条关系。
- [result.json](result.json)：实际执行工作流后生成的五条路径结果与源码文本 SHA-256。
- [运行脚本](../../scripts/demo/run-evidence-case.py)：从仓库根目录执行，无需 Key、Docker 或外部服务。

```powershell
conda run --no-capture-output -n AiJava python scripts/demo/run-evidence-case.py
# 需要更新本文件夹的结果时显式指定输出
conda run --no-capture-output -n AiJava python scripts/demo/run-evidence-case.py `
  --output examples/evidence-case/result.json
```

| 场景 | 实际 mode | degraded | 原因 |
| --- | --- | --- | --- |
| bm25 | bm25 | false | 无 |
| rerank | bm25_rerank | false | 无 |
| rerank_failed | bm25 | true | RERANK_FAILED |
| rerank_empty | bm25 | true | RERANK_EMPTY |
| no_evidence | none | false | 无证据；不表示真实服务健康 |

模型替身故意生成一条引用不存在的陈述。查看最终 `claims`、`citations` 和 `warnings`，可检查这条陈述已被移除，并确认 SSE `retrievalEvent` 与最终 `result.retrieval` 一致。重排替身故意交换 A/B 顺序以验证排序传递；失败与空结果场景应保持原顺序，这个分数不代表农业相关性。

实际使用的是本仓库的 ToolRegistry、RerankerGateway、AgentRuntime、MainAgentGraph 和 AgentService；候选检索、模型回答、图谱响应、重排 HTTP 响应为离线替身。本案例不验证 Elasticsearch 检索质量、Neo4j 联通性、视觉理解或真实模型效果，也不包含 UI 截图。源码摘要按 UTF-8 文件内容归一化 CRLF→LF 后计算。
