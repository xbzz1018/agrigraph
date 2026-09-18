# 脚本目录

- `data/`：公开数据下载、整理、许可审计和发布包构建。
- `graph/`：Neo4j 导入文件生成和 Cypher 导入入口。
- `evaluation/`：RAG 评测集生成与指标执行。
- `dev/`：Windows 本地启停、验收依赖编排和 UTF-8 日志查看。

Python 脚本统一用 `conda run -n AiJava python`。执行下载或处理脚本前先设置项目外的 `AGRIGRAPH_DATA_ROOT`，不要把原始大文件写入仓库。复现顺序见 [`../docs/runbook.md`](../docs/runbook.md)。

数据脚本不再包含个人机器盘符或 Anaconda 安装路径。可以显式传 `-DataRoot`，也可以设置
`AGRIGRAPH_DATA_ROOT`；Conda 未加入 `PATH` 时设置 `AGRIGRAPH_CONDA_EXE` 指向 `conda.exe`。
缺少这些配置时脚本会立即报错，不会退回源码目录或猜测本机路径。

完整本地演示先运行 `dev/start-acceptance-dependencies.ps1`，再运行根目录 `start-windows.bat`。依赖脚本生成的 `var/acceptance/infra.env` 只供本机容器和后端共享凭据，不替代保存模型密钥的 `.env.ai`。

最终自动验收使用 `dev/run-automated-acceptance.ps1`。默认执行完整质量门禁、数据刷新、Evidence QA 核心烟测、
Dev/Test V2 四路检索、40 条生成和 20x3 Stability，HTTP 请求超时为 600 秒。候选摘要写入被忽略的
`var/reports/`，只有全部冻结门槛通过才标记 `COMPLETED_CANDIDATE`。`-SkipQualityGates`、
`-SkipDataRefresh` 和 `-SkipEvaluation` 仅供定位失败和局部重试，
不能替代默认完整运行。`graph/import-acceptance-neo4j.ps1` 只向验收容器幂等导入图谱，不删除数据卷。

本项目不包含知识治理、审批发布或可信搜索演示脚本；评测只围绕检索、证据回答和安全审查展开。
