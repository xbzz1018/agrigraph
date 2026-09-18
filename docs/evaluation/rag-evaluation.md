# 多模态知识服务评测

本项目对外只展示三个指标组，不把内部 Token、成本、节点耗时或 Stability 作为核心农业成果。

## 文本知识问答

使用番茄/水稻病虫害样本，固定 Elasticsearch BM25，报告候选病虫害 `Recall@10`、`MRR`、`nDCG@10`、Claim Coverage、Citation Coverage 和 Citation Correctness。

## 图片症状理解

从外部公开且已核验的图片中冻结番茄 15 张、水稻 15 张，保存图片 SHA-256、来源、许可证、作物、部位、症状和标准实体 ID。图片模型只输出 `VisionObservation`，指标为结构化字段成功率、症状词覆盖率和候选病虫害 `Recall@3`。

## 防治关系

对人工核验的病害—农业防治、生物防治、有效成分关系计算 `Recall@5` 与正确率，同时检查剂量、浓度、倍液、混配和施药次数泄漏率，泄漏率必须为 0。

## 评测边界

新参数先在 Dev 选择后冻结，再执行 Test。评测报告使用源码清单、数据、Prompt、工具 Schema 和工作流的 SHA-256；无 Git 时标记 `sourceState=UNVERSIONED_LOCAL`，不伪造 commit。

任何模型失败、样例缺失、Neo4j/ES 降级或安全边界失败都不能生成通过状态的候选报告。
