# CONTEXT.md — Lingya 术语表

Lingya = 个人跨 harness 的金蝶 ERP 开发工具集。本文只定义术语,不写实现。

## 核心术语

**Harness(宿主)**
调用本工具集的 AI agent 运行环境。当前梯队:灵基 build 模式、ZCode、opencode。判定标准:能开 shell 执行命令、能读 SKILL.md 说明书的 agent 环境。

**ly**
本工具集的 CLI 命令名与总入口。`ly` 是唯一的能力载体,SKILL.md 只是它的说明书。

**SKILL.md 包装**
面向 harness 的说明书文件(Agent Skills 格式),不承载逻辑,只教 agent 如何发现和调用 ly。同一份 SKILL.md 服务所有 harness;不支持 skills 机制的 harness 退化为"直接读该文件"。

**JSON 信封**
ly 的输出契约:成功 = stdout 输出 `{"ok":true,"data":...,"meta":...}` 且退出码 0;失败 = stderr 输出 `{"ok":false,"error":{type,code,message,hint}}` 且退出码非 0。agent 判 `ok` 或退出码,不判业务码。

**环境(ERP Environment)**
一套可连接的金蝶服务端连接配置(五要素:环境地址 URL、账套 accountId、应用 client_id、应用密钥 client_secret、用户名,可选:数据中心 datacenter、网关标识 x-acgw-identity)。环境存储与灵基客户端"环境管理"同源,一处配置两处可用(ly 与灵基 build 技能)。

**苍穹(Cosmic)**
金蝶企业级 PaaS 平台。用户本地轻量级环境即苍穹(登录页 `/ierp/login.html`)。ly 的第一目标平台。

**星空(K3 Cloud)**
金蝶公有云 ERP 产品。ly 的第二阶段目标(路线:本地苍穹 → 星空公有云 → 完整二开)。

## 易混概念

- **灵基 Work 模式的"ERP环境"**(云端会话级账套绑定,经 Kingdee-SaaS 云端 MCP)≠ **Build 模式的"ERP环境"**(环境管理里的五要素直连)。前者在本地劫持形态下不可用,后者可用。本工具集只依赖后者,不依赖前者。
- **灵基点数/席位**(灵基商业模式)与 **ERP 账套授权**(金蝶侧)是两回事;ly 路线不消耗灵基点数。
- **应用密钥授权(enhanced)**:单步 getToken,无需用户密码;配置里**永不存登录密码**。

## 红线

- API key、应用密钥、cookie 等凭证只存本地 config(`~/.kd/config.json` 等),绝不提交任何仓库、不出现在聊天记录里。
- 官方 RAG/社区接口保持人类使用频率,勿高频。
