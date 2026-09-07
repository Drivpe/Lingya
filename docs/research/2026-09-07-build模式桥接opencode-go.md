# 灵基 build 模式桥接 opencode-go —— 调研与验证记录

> 日期:2026-09-07 | 结论:**build(开发)模式早已桥接完成,本次验证 key 有效并修复了断掉的代理链路**
> 关联交接文档:2(Windows落地/引擎解剖)、4(工作模式落地)、6(三级链路/opencode-go 首接)

## 0. 问题

用户问:灵基(安装于 `C:\01_Programs\03_Development_Tools\Lingee`)的 build 模式能否桥接其他模型供应商(如 opencode go),并提供新密钥(sk-ucIK…cj402)。

## 1. 结论

**可以,而且早已打通。** 交接文档 6 §2.7 记录:opencode-go(OpenAI 兼容,`https://opencode.ai/zen/go/v1`)已通过 model-proxy(4090)接入并端到端验证。本次核实:

- `C:\Users\Drivpe\.lingeebuild\config\model-map.json` 中 `opencode-go` 的 apiKey **已是用户本次提供的同一把 key**,全部档位/模型名均映射到 `opencode-go/glm-5.3-flash`
- key 直连验证通过(2026-09-07 实测):`POST https://opencode.ai/zen/go/v1/chat/completions` 用 glm-5.3-flash 返回完整补全,`cost` 字段正常计费
- 端到端验证通过(2026-09-07):引擎 4096 建会话发消息 → 代理日志实锤路由 `deepseek-v4-flash -> opencode-go/glm-5.3-flash` → 真实回复("1 + 1 = 2"),HTTP 200

## 2. 本次发现并修复的问题(链路当时是断的)

| # | 问题 | 根因 | 处置 |
|---|---|---|---|
| 1 | 4090 代理、4095 shim 全没在跑 | 电脑重启后 WSL `/tmp` 清空,`stack_supervisor.sh` 日志目录不存在启动失败;4096 被客户端 kcode-serve 抢占 | 补建目录拉起后又遇问题 2,最终改用 Windows 原生方案 |
| 2 | Windows 侧绑定 4090 报 WinError 10013 | **WSL 镜像网络模式**下,WSL 内 python3 绑定的 0.0.0.0:4090 会阻止 Windows 绑定同端口 | kill WSL 残留进程(pid 45/55)后释放 |
| 3 | 顺手踩了 `pkill -f` 自杀坑 | 命令行含匹配字样杀掉自己的 shell | 改 kill PID(交接文档 7/18 已两次记录此坑) |

**修复方案**:模型代理改为 **Windows Python 3.12 直跑**(model-proxy.py 本身 Windows 兼容,日志写 `config\proxy.log`),摆脱 WSL 依赖。`start-lingee-stack.ps1` 升级 v3:
- 代理用 Windows Python 启动(已在跑则跳过),不再起 WSL 看门狗
- 启动前先清理 WSL 残留的 4090/4095 监听(防 10013 复发)
- 修复了原文件的双 BOM 编码错误(首行 `?#` 报错)
- 已实测:v3 一键启动 → 4096/4090 就绪 → 端到端回复正常

## 3. 当前链路(验证于 2026-09-07)

```
灵基客户端 开发/build 模式(webview)
  → 引擎 serve 4096(我们的 lingeebuild.exe serve,读 config\opencode.json)
  → model-proxy 4090(Windows Python,model-map.json 热生效)
  → https://opencode.ai/zen/go/v1(opencode-go,glm-5.3-flash)
```

模型名解析优先级与坑见交接文档 2 §3.5、6 §2.7(引擎侧只认 opencode.json 里定义的 provider 名,真实路由由 model-map.json 负责,改它无需重启引擎)。

## 4. 未随本次恢复的组件(非 build 模式依赖)

- **work-shim(4095/41443,工作模式)**:work-shim.py 硬编码 `/tmp` 路径,Windows 直跑会挂;WSL 版受问题 1/2 影响。需要工作模式时另行修复(移植 Windows 或修 WSL 目录)
- **rag-bridge(4097,金蝶文档)**:独立服务,用 `start-kingdee-rag.ps1` 单独拉起(vip cookie 可能已过期需重收割)

## 5. 证据索引

| 证据 | 位置 |
|---|---|
| key 配置与全档位映射 | `C:\Users\Drivpe\.lingeebuild\config\model-map.json` |
| key 直连 + e2e 计费 | proxy.log `in-model: deepseek-v4-flash -> opencode-go/glm-5.3-flash`;上游返回含 `cost` 字段 |
| e2e 真实回复 | 4096 会话 `ses_*` 回复 "1 + 1 = 2",HTTP 200(2026-09-07 07:31) |
| v3 启动脚本 | `C:\Users\Drivpe\.lingeebuild\start-lingee-stack.ps1` |

## 6. 安全提醒(沿交接文档红线)

- opencode-go key 与所有 cookie 仅存于本地 config 目录(无 git 仓库),勿提交、勿外传
- 建议尽快在 opencode 后台轮换本次已出现在对话记录中的 key
