# Lingya

个人跨 harness 的金蝶 ERP 开发工具集。核心是 `ly` CLI(苍穹/星空 OpenAPI),配一份 SKILL.md 让所有 AI agent 宿主(灵基 build / ZCode / opencode)统一调用。

详见 [CONTEXT.md](CONTEXT.md)(术语表)与 [docs/adr/](docs/adr/)(架构决策)。

## 安装

```bash
pip install -e .
ly --version
```

要求 Python ≥ 3.10,零第三方依赖(纯标准库)。

## 快速开始

```bash
# 1. 添加环境(五要素;写 ~/.kd/config.json,与灵基环境管理同源)
ly auth add --name local-cosmic --url http://127.0.0.1:8080/ierp \
  --account-id <数据中心id> --client-id <appId> --client-secret <appSecret> \
  --username <代理用户> --acgw <网关标识,如有> --default

# 2. 体检
ly doctor

# 3. 用起来
ly meta query-forms --params '{"keyword":"BAS"}'
ly meta biz-apps
ly api GET /kapi/v2/devportal/ai-meta/getDevInfo
```

## 输出契约(JSON 信封)

- 成功:stdout `{"ok":true,"data":...,"meta":{...}}`,退出码 0
- 失败:stderr `{"ok":false,"error":{"type","code","message","hint"}}`,退出码 1

## 写操作门

`ly` 的 write-mode 出厂默认 `confirm`:一切非 GET 请求(含 `ly api` 透传)默认只返回请求预览,加 `--confirm` 才真正执行;`ly config set write-mode free` 一键永久放开(agent 自由写入);`--dry-run` 任何模式下都只看预览。不记审计日志(决议见 issue #3)。

## 路线图

- [x] v0.1 auth(getToken/verify/withdraw)+ meta 只读查询 + api 透传 + doctor
- [x] v0.1.1 写操作门(write-mode confirm/free)+ ly config 命令
- [ ] v0.2 数据查询/写操作(业务 API 为「对象×操作」发布式路由,需表单→操作API映射;见 issue #2 调研)
- [ ] v0.3 与灵基 app-build 技能协同的元数据二开(buildMeta/modifyMeta/插件)
- [ ] v0.4 星空适配(K3 Cloud 是分支逻辑:LoginBySign 签名会话;旗舰版则近零适配;见 issue #7 调研)

## 宿主接入

- **灵基 build**:把 `skills/ly/` 复制到 `C:\Users\<user>\.lingeebuild\config\builtin-skills\ly`
- **ZCode / Claude Code**:把 `skills/ly/` 放入对应 skills 目录
- **opencode**:无 skills 机制时,在指令中让它读 `skills/ly/SKILL.md` 文件即可

## 安全红线

凭证只存本地 `~/.kd/config.json`(在 git 仓库之外),绝不提交、绝不进聊天记录。认证限流 30 次/分,密钥错误有锁定机制,禁止暴力重试。
