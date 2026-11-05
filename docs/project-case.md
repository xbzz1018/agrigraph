# AgriGraph：让症状问答留下可检查的依据

[返回首页](../README.md) · [可运行案例](../examples/evidence-case/README.md) · [验证记录](acceptance/public-verification.md)

## 业务问题

同一种叶片症状可能对应多个病虫害，图片也可能缺少诊断所需的环境信息。单独让模型回答，无法解释候选来自哪里，也难以判断哪些陈述有资料支持。

本项目围绕番茄和水稻，把输入观察、候选召回、图谱关系与回答证据分开。用户可以核对候选和引用，再交给农技人员判断；系统不承担直接确诊或给出具体用药参数的职责。

## 我的工作

我完成公开资料的工程实现：用 AgricultureQuery / VisionObservation 统一输入，设计固定 LangGraph 工作流与工具权限，把 Elasticsearch、外部重排和 Neo4j 限制在各自边界内，补上 Claim 引用核验、输出过滤、SSE 运行审计和评测脚本。

个人贡献范围是本仓库公开资料的独立实现；历史实习经历另行说明。

## 案例：有症状，还需要什么依据

离线输入：“番茄叶片出现褐色斑点，应如何查找依据？”

为便于无凭据复现，案例使用明确标注的合成候选 A/B，而不是复制农业原文或历史模型回答。执行结果见 [result.json](../examples/evidence-case/result.json)。

| 步骤 | 可以检查的产物 |
| --- | --- |
| 结构化查询 | 作物为番茄，任务为症状检索 |
| 候选取证 | `doc:demo-a` / `doc:demo-b`，各自保留摘录与检索元数据 |
| 图谱关系 | 候选 A → HAS_SYMPTOM → 褐色斑点 |
| 回答核验 | “叶片可见褐色斑点”引用 `doc:demo-a`；引用缺失的断言被移除 |
| 对外结果 | `claims`、`citations`、`graphRelations`、`warnings` 与实际 `retrieval` |

可复跑的输入、输出和源码摘要构成本案例的检查材料。真实知识质量需要在真实资料、模型和冻结样本上另行评测。

## 工程取舍

**图像先转观察。** VisionObservation 只保存作物、部位、症状与质量提示，再转为 AgricultureQuery。文字与图片因此复用同一检索链路，视觉模型的猜测也不会直接变成结论。

**候选检索与关系解释各自取证。** Elasticsearch 按名称、症状、病原和发生条件召回资料；Neo4j 补充症状、病原、发生条件和防治之间的关系。Answer 只消费取证结果。

**重排按问题类型启用。** SYMPTOM / CONDITION 问题在服务已配置时进入重排。配置决定是否尝试，实际返回证据决定本次 `mode`；模型配置存在不意味着本次调用成功。

**记忆与事实证据分开。** 历史对话帮助理解“它”“这种情况”。记忆放在独立上下文中，Claim 核验只消费文档和图谱证据。

**引用核验有明确范围。** 当前规则检查证据 ID 和文本支持程度。来源是否可靠、陈述是否符合事实、近似文本匹配是否误判，以及图片症状是否遗漏，仍需人工复核。

## 失败案例：重排不可用时如何解释结果

原问题是 SSE 总是写 `bm25`，即使条件重排执行成功，也无法从事件中分辨。PR #27 将健康检查中的配置策略与每次运行的实际检索分开：

| 情况 | 最终模式 | 降级信号 |
| --- | --- | --- |
| 未启用重排 | bm25 | 无 |
| 重排成功 | bm25_rerank | 无 |
| 重排 HTTP 失败 | bm25 | degraded=true / RERANK_FAILED |
| 重排返回空结果 | bm25 | degraded=true / RERANK_EMPTY |
| 没有文档证据 | none | 不推断外部服务健康 |

降级时保留 BM25 顺序，事件只输出稳定原因码，不返回外部响应正文。离线案例同时检查最终结果和 `retrieval_result` 事件；真实网络与真实 Reranker 尚需独立验收。

## 验证与交付

- 交付代码、运行手册、固定评测集、公开脱敏摘要和五条离线案例，读者可以沿产物追到实现与测试。
- 历史候选包含 160 条文本检索、40 条回答生成、30 张图片、30 条防治关系记录，但没有 Git commit 和执行日期，不能作为当前版本通过证明。
- 历史图片候选 Recall@3 为 1.0，而症状覆盖率仅 0.1278。这说明候选命中与观察完整性需要分开报告，不能仅展示较高的一个指标。
- 当前源码与完整数据栈、模型组合的联合验收仍待执行；本次不使用历史数据补写当前成绩。

## 从代码追问

| 问题 | 实现入口 |
| --- | --- |
| 谁能调用哪些工具？ | [tools.py](../backend-python/app/agents/tools.py) |
| 节点为何按固定顺序执行？ | [chat_graph.py](../backend-python/app/agents/chat_graph.py) |
| 如何过滤无证据陈述？ | [runtime.py](../backend-python/app/agents/runtime.py) |
| 实际检索模式如何进入 SSE？ | [schemas.py](../backend-python/app/agents/schemas.py)、[chat_service.py](../backend-python/app/agents/chat_service.py) |
| 如何复核成功、降级和无证据路径？ | [契约测试](../backend-python/tests/agents/test_retrieval_contract.py)、[案例回归](../backend-python/tests/agents/test_evidence_demo.py) |
