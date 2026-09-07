---
name: ly
description: 个人金蝶 ERP 开发 CLI(苍穹/星空 OpenAPI)。查询金蝶元数据(表单/字段/应用)、调用苍穹 OpenAPI、诊断 ERP 环境连接时使用。当用户提到苍穹、星空、ERP、元数据、表单、账套、开发环境时触发。
---

# ly — 金蝶 ERP 开发 CLI

本领在 `ly` 命令里,本文件只是说明书。任何 harness(灵基 build/ZCode/opencode)通用。

## 铁律

1. **记住本文件所在目录的绝对路径(下称 `${LY_SKILL_DIR}`),展开引用;不依赖 CWD,不要 `cd`。**
2. ly 的所有输出是 **JSON 信封**:成功 = stdout `{"ok":true,"data":...}` 且退出码 0;失败 = stderr `{"ok":false,"error":{type,code,message,hint}}`。**先判 `ok` 或退出码,再取 data**。
3. 凭证在 `~/.kd/config.json`(与灵基环境管理同源),**永远不要把 client_secret 打进对话或写入任何仓库文件**。
4. 认证有限流(30次/分)和**密钥错误锁定**——getToken 报 401 时,提示用户核对密钥,禁止连续重试。
5. **写操作门**:`ly` 的 write-mode 默认 `confirm`——一切非 GET 请求(含 `ly meta build-meta/modify-meta`、`ly api POST/PUT/DELETE`)默认只返回请求预览不执行;正确姿势:先跑一次拿预览 → 给用户看 → 用户点头后加 `--confirm` 重跑。用户明确说过"放开"时才可 `ly config set write-mode free` 永久关闭门(之后无需 --confirm)。任何时候都可加 `--dry-run` 只看预览。
6. Git Bash/MSYS 宿主:URL path 参数会被改写成 Windows 路径,ly 会自动还原;若异常,命令前加 `MSYS_NO_PATHCONV=1`。

## 常用命令

```bash
ly doctor                                     # 体检:配置→连通→认证,任何问题先跑这个
ly auth show                                  # 查看当前环境(密钥打码)
ly auth add --name prod --url https://host/ierp --account-id <id> --client-id <appId> --client-secret <secret> --username <user> [--acgw <网关标识>] [--default]
ly auth login                                 # 取 token 并缓存(2h 有效,自动续)
ly auth test                                  # verifyToken 验证
ly auth logout                                # 撤回 token 并清缓存

ly meta query-forms --params '{"keyword":"BAS"}'    # 按关键词查表单
ly meta biz-apps                                    # 业务应用列表
ly meta form-schema --params '{"formNumber":"..."}' # 表单 schema
ly meta entity-fields --params '{"formNumber":"..."}' # 实体字段

ly meta build-meta --data '<buildMeta 需求产物 JSON>' [--confirm]   # 新建表单(设计器建模)
ly meta modify-meta --data '<modifyMeta MetaOps JSON>' [--confirm]  # 已有表单增/删/改字段与实体

ly api GET /kapi/v2/devportal/ai-meta/queryForms --params '{"keyword":"X"}'   # 任意端点兜底
ly config set write-mode free                       # 关闭写操作门(用户明确要求后才做)
```

环境选择:`-e <环境名>`;缺省取 `isDefault`。

## 渐进加载

按需读取 references,不要一次读全:
- 端点细节(元数据/操作/插件管理全表)→ `${LY_SKILL_DIR}/references/endpoints.md`
