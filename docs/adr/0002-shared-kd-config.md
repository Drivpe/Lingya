# 0002 — 环境配置与灵基环境管理同源(~/.kd/config.json)

日期:2026-09-07 | 状态:已接受

## 背景

ly 需要存苍穹/星空环境五要素(URL/账套/应用ID/应用密钥/用户名+网关标识)。灵基客户端 Build 模式「设置→环境管理」已有一套环境配置,落在 `~/.kd/config.json` 的 `env` 段,其内置技能(app-build 的 kd_auth.py/kd_env_loader.py)按固定字段名读取。

## 决策

**ly 不自建配置存储,直接读写 `~/.kd/config.json` 的 `env` 段(双写 camel/snake 两种字段名风格)。** ly 的 token 缓存独立放 `~/.ly/`。

## 理由

- 一次配置两处可用:在 ly 里 `ly auth add`,灵基 build 模式的 app-build/kd-frontend-development 技能立即可用同一环境;反之亦然。
- 字段语义已由灵基生产代码验证(kwork token_cache.py 同源),降低认证字段猜错成本。
- 凭证集中一处,便于审计与保护(该文件在 git 仓库之外)。

## 后果

- ly 必须容忍灵基侧写入的配置形态(dict 或 list、可选字段缺失)——config.py 做了兼容归一。
- 若灵基客户端升级改变配置结构,ly 需同步(升级韧性检查项)。
- 密钥在该文件明文存放(灵基侧另有 DPAPI 加密缓存机制,文件本身明文)——文件权限与红线约束不变:不入仓库、不入聊天。
