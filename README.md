# Lingya

![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)
![Zero-dependency](https://img.shields.io/badge/deps-zero-green.svg)
![AI-first](https://img.shields.io/badge/design-AI--first-8A2BE2.svg)

**ly —— agent 改金蝶 ERP 的金手指:一个纯标准库的苍穹/星空 OpenAPI CLI + 一份跨 harness 通用的 SKILL.md。**

查元数据、建模二开(建表单/改字段/改操作/挂校验)、透传任意 OpenAPI,全部经 JSON 信封返回——让灵基 build、ZCode、opencode 等任意 AI agent 宿主用同一套姿势干活。

[为什么选 ly](#为什么选-ly) · [安装](#安装) · [命令](#命令速查) · [JSON 契约](#json-契约ai-first) · [写操作门](#写操作门) · [安全](#安全红线)

> **Note for AI assistants**:① 先读 [skills/ly/SKILL.md](skills/ly/SKILL.md)(说明书,含铁律与端点细节索引),不要凭想象拼命令;
> ② 所有输出是 JSON 信封,先判 `ok`/退出码再取 `data`;③ 一切非 GET 请求默认被写操作门拦下,预览确认后加 `--confirm` 才执行。

## ⚠️ 使用前必读

- 需要**已获授权的金蝶环境**(账套 id / 应用 id+密钥 / 用户名),凭证只存本地 `~/.kd/config.json`,本仓库零凭据;
- 写操作默认有 confirm 门,agent 不会静默改你的 ERP;
- 认证限流 30 次/分,密钥错误有锁定机制,禁止暴力重试。

## 为什么选 ly?

- **为 agent 原生设计** —— 默认 JSON 信封:成功 = stdout `{"ok":true,"data":...}` + 退出码 0;失败 = stderr 带 `type/code/message/hint` 的 JSON + 退出码 1,`hint` 直接给修复指引;永不交互
- **零依赖** —— Python 纯标准库,`pip install -e .` 即用,无供应链面
- **跨 harness 一份说明书** —— SKILL.md 包装不承载逻辑只教调用;支持 skills 机制的宿主装上即用,不支持的让它读文件即可
- **写操作门** —— confirm(默认,预览后 `--confirm` 放行)/ free(一键放开)/ `--dry-run` 任何模式可看预览,agent 自由度可调
- **元数据二开全链路实测跑通** —— 查表单/字段 → 扩展表单 → 改操作/挂校验,全部经 API 完成,无需 JDK、无需打开设计器
- **与灵基同源** —— 环境配置与灵基客户端"环境管理"同一份 `~/.kd/config.json`,一处配置两处可用

## 功能

| 域 | 能力 |
|---|---|
| 🔐 auth | 环境管理(五要素,多环境 `--name` 切换)/ 登录取 token(2h 自动续)/ 验证 / 撤回 |
| 🔍 meta 查询 | 按关键词查表单、业务应用列表、表单 schema、实体字段 |
| 🏗️ meta 二开 | `build-meta` 新建表单(设计器建模)、`modify-meta` 已有表单增删改字段与实体(MetaOps) |
| ⚙️ 操作管理 | 经 api 透传 devportal ai-meta 端点:操作增删改查、操作校验(条件/唯一性/必录等)全生命周期 |
| 🔌 api 透传 | `ly api GET/POST/PUT/DELETE` 兜底任意未包装端点,同样受写操作门保护 |
| 🩺 doctor | 配置→连通→认证一站式体检,任何问题先跑它 |
| 🚪 config | `write-mode` confirm/free 切换等本地设置 |
| 📦 技能包装 | `skills/ly/SKILL.md` + `references/`(端点全表与踩坑实证),复制即接入 |

## 安装

### ① 常规(推荐)

```bash
pip install -e .
ly --version
```

要求 Python ≥ 3.10,零第三方依赖。

### ② 开发者

```bash
git clone https://github.com/Drivpe/Lingya.git && cd Lingya
pip install -e .
ly doctor   # 装完先体检
```

### ③ AI Agent 接入(三行)

```text
1. 读 skills/ly/SKILL.md —— 命令契约与铁律(先判 ok 再取 data;非 GET 需 --confirm)
2. ly auth add 配好环境后跑 ly doctor 确认三绿灯
3. 需要端点细节时再读 skills/ly/references/endpoints.md(端点全表+踩坑实证),不要猜
```

宿主落位:灵基 build 复制到 `C:\Users\<user>\.lingeebuild\config\builtin-skills\ly`;ZCode / Claude Code 放入对应 skills 目录;opencode 直接在指令里让它读 SKILL.md。

## 快速开始

```bash
# 1. 添加环境(五要素;写 ~/.kd/config.json,与灵基环境管理同源)
ly auth add --name local-cosmic --url http://127.0.0.1:8080/ierp \
  --account-id <数据中心id> --client-id <appId> --client-secret <appSecret> \
  --username <代理用户> --acgw <网关标识,如有> --default

# 2. 体检
ly doctor

# 3. 用起来
ly meta query-forms --params '{"keyword":"BAS"}'   # 查表单
ly meta biz-apps                                   # 业务应用列表
ly meta entity-fields --params '{"formNumber":"..."}'  # 实体字段
ly api GET /kapi/v2/devportal/ai-meta/getDevInfo   # 任意端点兜底
```

## 命令速查

| 命令 | 作用 |
|---|---|
| `ly auth add --name <env> --url <ierp> --account-id <id> --client-id <appId> --client-secret <secret> --username <user> [--acgw <标识>] [--default]` | 添加环境 |
| `ly auth login` / `ly auth test` / `ly auth logout` / `ly auth show` | 取 token / 验证 / 撤回 / 查看(密钥打码) |
| `ly doctor` | 配置→连通→认证一站式体检 |
| `ly meta query-forms --params '{"keyword":"X"}'` | 按关键词查表单 |
| `ly meta biz-apps` | 业务应用列表 |
| `ly meta form-schema --params '{"formNumber":"..."}'` | 表单 schema |
| `ly meta entity-fields --params '{"formNumber":"..."}'` | 实体字段 |
| `ly meta build-meta --data '<JSON>' [--confirm]` | 新建表单(设计器建模) |
| `ly meta modify-meta --data '<JSON>' [--confirm]` | 已有表单增删改字段与实体 |
| `ly api GET/POST/PUT/DELETE <path> [--params '<JSON>'] [--data '<JSON>'] [--confirm]` | 任意端点兜底 |
| `ly config set write-mode confirm\|free` | 写操作门模式切换 |

环境选择:`-e <环境名>`;缺省取 `isDefault`。

## JSON 契约(AI-first)

- 成功:stdout `{"ok":true,"data":...,"meta":{...}}`,退出码 0
- 失败:stderr `{"ok":false,"error":{"type","code","message","hint"}}`,退出码 1
- `hint` 带修复指引;**先判 `ok` 或退出码,再取 `data`**,不判业务文案
- 认证有限流(30 次/分)与密钥错误锁定; getToken 报 401 提示核对密钥,禁止连续重试
- Git Bash/MSYS 宿主下 URL path 参数会被改写成 Windows 路径,ly 自动还原;异常时命令前加 `MSYS_NO_PATHCONV=1`

## 写操作门

`ly` 的 write-mode 出厂默认 `confirm`:一切非 GET 请求(含 `ly api` 透传)默认只返回请求预览,加 `--confirm` 才真正执行;`ly config set write-mode free` 一键永久放开(agent 自由写入);`--dry-run` 任何模式下都只看预览。不记审计日志(决议见 issue #3)。

## 路线图

- [x] v0.1 auth(getToken/verify/withdraw)+ meta 只读查询 + api 透传 + doctor
- [x] v0.1.1 写操作门(write-mode confirm/free)+ ly config 命令
- [x] v0.2.0 元数据二开写通道(build-meta / modify-meta)+ 操作与校验全生命周期(经 api 透传 devportal ai-meta)
- [ ] v0.3 业务数据通道(`ly data` 命令;业务 API 为「对象×操作」发布式路由,见 issue #2 调研)
- [ ] v0.4 星空适配(K3 Cloud 是分支逻辑:LoginBySign 签名会话;旗舰版则近零适配;见 issue #7 调研)
- [ ] v0.5 扩展表单全流程包装(extendForm / enableDisable / 插件注册)

## 术语与决策

- [CONTEXT.md](CONTEXT.md) —— 项目术语表(harness / JSON 信封 / 元数据二开 / 写操作门 / 扩展表单 / 坏引用探针等)
- [docs/adr/](docs/adr/) —— 架构决策记录(CLI+Skill 优于 MCP、共享 kd 配置等)
- [docs/research/](docs/research/) —— 调研笔记(kapi 数据端点选型、星空/苍穹差异等)

## 安全红线

- 凭证只存本地 `~/.kd/config.json`(在 git 仓库之外),绝不提交、绝不进聊天记录、绝不写入任何文档
- 认证限流 30 次/分,密钥错误有锁定机制,禁止暴力重试
- 写操作门是最后一道闸:confirm 模式下 agent 不可能静默改 ERP
- 公开仓库即公开接口用法,本工具面向个人授权环境使用,请遵守金蝶服务条款

## License

MIT —— 见 [LICENSE](LICENSE)。
