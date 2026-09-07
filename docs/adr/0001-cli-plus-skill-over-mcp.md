# 0001 — ly 采用「CLI 核心 + 薄 SKILL.md 包装」而非 MCP

日期:2026-09-07 | 状态:已接受

## 背景

ly 要被多个 AI agent 宿主(灵基 build、ZCode、opencode)调用。候选形态:MCP server、CLI(被 agent bash 调用)、纯 SKILL.md(prompt+脚本)。

## 决策

**CLI 为核心能力载体 + 一份 SKILL.md 作为所有宿主统一的说明书;MCP 后置为可选适配层,不作为核心形态。**

## 理由

1. **宿主覆盖**:MCP 需要每个客户端各自配置,且灵基本地劫持形态下 `query_mcp_tools` 不可用(实测,见交接文档4/10);CLI 只要宿主能开 shell 就能用,零接入成本。
2. **能力发现**:CLI 的弱项(自发现差)由 SKILL.md 弥补——skill 只是说明书,本领在 CLI 里,换宿主只需换/省说明书。ppt-master(52k stars,纯 SKILL.md)与 lark-cli(CLI+26 个 SKILL.md)分别验证了两个组件的可行性。
3. **输出可靠**:借鉴 lark-cli 的 JSON 信封契约(ok/data/error + 退出码语义),任何 agent 都能可靠解析。
4. **长任务旁路**:大文件落盘,不占 agent 上下文。

## 后果

- 换宿主零成本;MCP 若将来需要(如非 shell 宿主),在 CLI 之上包一层即可。
- SKILL.md 必须带 `${LY_SKILL_DIR}` 硬规则(不依赖 CWD),沿用 ppt-master 的跨宿主经验。
