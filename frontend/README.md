# Vue 前端

本目录是 Vue 3 + TypeScript + Naive UI 前端。主要业务页位于 `src/views`，Agent 时间线位于 `src/components/agent`，POST SSE 解析位于 `src/utils/sse.ts`。

```powershell
pnpm install --frozen-lockfile
pnpm dev
pnpm typecheck
pnpm build
```

`packages/` 只保留仍被工作区引用的模板基础包。`src/router/elegant` 和部分类型声明由工具生成，不在生成文件中添加教学注释。系统边界见 [`../docs/architecture.md`](../docs/architecture.md)。
