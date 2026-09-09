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

**元数据二开(Metadata 二开)**
通过苍穹元数据服务新建/修改表单与字段(建字段、改表单)的二开方式,无需 JDK。ly 的首选路线;到达终点(端到端二开)的既定路径。

**插件开发(Plugin Development)**
agent 写 Java → 编译 → 经插件注册接口挂载的完整二开路线,依赖本机 JDK。作为元数据二开之后的后续里程碑,不在首跑范围。

**端到端二开(End-to-End 二开)**
地图终点的判定形态:查基线元数据 → 经写通道修改 → API 读回验证生效。UI 人工验证为可选加分项,不计入 agent 判定标准。

**实验床(Experiment Bed)**
经用户决定**常驻**的 BOTP 测试资产(自建表单 A/B、A→B 转换规则、已发布 push/query API,及实验产生的单据实例),专供写链路实验。不承载业务、不碰财务单据。2026-09-09 起取代原「测试表单验收末尾反向删除」规矩——原铁律整条废止。

**扩展表单(Extended Form)**
对标准表单做二开的载体。操作/校验的修改落在**共享实体的元数据行**上,原表单运行时直接生效,不依赖扩展表单自身合并;但扩展表单须启用,停用态不并入运行时元数据。

**坏引用探针(Bad-Reference Probe)**
运行时可证伪的排障手法:故意写入不存在的字段引用,若运行时报「字段已不存在」类配置错误,即证明校验器在执行且元数据已合并,从而把「没生效」二分定位到具体环节。用于代替纯静态推断。

## 易混概念

- **灵基 Work 模式的"ERP环境"**(云端会话级账套绑定,经 Kingdee-SaaS 云端 MCP)≠ **Build 模式的"ERP环境"**(环境管理里的五要素直连)。前者在本地劫持形态下不可用,后者可用。本工具集只依赖后者,不依赖前者。
- **灵基点数/席位**(灵基商业模式)与 **ERP 账套授权**(金蝶侧)是两回事;ly 路线不消耗灵基点数。
- **应用密钥授权(enhanced)**:单步 getToken,无需用户密码;配置里**永不存登录密码**。

## 红线

- API key、应用密钥、cookie 等凭证只存本地 config(`~/.kd/config.json` 等),绝不提交任何仓库、不出现在聊天记录里。
- 官方 RAG/社区接口保持人类使用频率,勿高频。
