# Lingya 调研笔记：转换规则配置 & 自建单据测试

> 调研日期：2026-09-07（本地优先，GitHub 核对于同日本文标注处）
> 目的：为两个后续功能开发做准备——① 前台转换规则配置；② 开发平台配置自建单据测试。
> 方法：通读本地 `D:\01_Work\03_Develop\Lingya`（排除 `kingdee-knowledge-kit/` 独立子仓与 gitignore 的 `灵基模型切换-交接文档*.md`），并用 WebFetch 核对 GitHub 远程。

---

## 1. 项目概览

**Lingya = 个人跨 harness 的金蝶 ERP 开发工具集**。核心是 `ly` CLI（苍穹/星空 OpenAPI 客户端），配一份 `skills/ly/SKILL.md` 作为所有 AI agent 宿主（灵基 build / ZCode / opencode）统一的「说明书」。

- 一句话定位：`ly —— agent 改金蝶 ERP 的金手指：一个纯标准库的苍穹/星空 OpenAPI CLI + 一份跨 harness 通用的 SKILL.md`。来源：`README.md:8`、`CONTEXT.md:3`。
- 设计哲学：AI-first，所有输出走 **JSON 信封**（`{"ok":true,"data":...}` / 失败 `{"ok":false,"error":{type,code,message,hint}}`），永不交互。来源：`README.md:25`、`CONTEXT.md:16-17`、`skills/ly/SKILL.md:13`。
- 技术栈：**Python ≥ 3.10，零第三方依赖（纯标准库）**；`pip install -e .`，入口 `ly = "ly.cli:main"`。来源：`pyproject.toml`、`README.md:26`。
- 当前版本：**v0.2.0**。已实现：auth、meta 只读、meta 写（build-meta/modify-meta）、操作与校验全生命周期（经 api 透传）、api 兜底、doctor、写操作门。来源：`pyproject.toml:3`、`README.md:122-129`、`src/ly/cli.py:23-39`。

> 注意：仓库里另有一个 `kingdee-knowledge-kit/`（独立 git 子仓、被 `.gitignore` 排除），是 **匿名知识检索套件（`kd` CLI / ksearch 服务），只查金蝶官方文档/社区问答，不参与 ERP 开发操作**，与 `ly` 是两个独立项目。来源：`kingdee-knowledge-kit/README.md:7`、`.gitignore`（`kingdee-knowledge-kit/` 独立仓库行）。

---

## 2. 架构与数据流

**命令三层**（来源：`src/ly/cli.py:1-39`、`skills/ly/SKILL.md`）：

```
ly auth        环境管理 + 取 token（2h 缓存 ~/.ly/）
ly meta        ① 只读查询（queryForms/bizApps/formSchema/entityFields… 9 个 GET 端点）
               ② 元数据写（buildMeta 新建表单 / modifyMeta 改字段与实体）→ 走写操作门
ly api         GET/POST/PUT/DELETE 任意端点兜底（含操作/插件管理端点）
ly config      write-mode confirm|free 切换
ly doctor      配置→连通→认证 一站式体检
```

**模块划分**（`src/ly/`，来源：`src/ly/cli.py`、目录 `find src/ly`）：
- `cli.py`：argparse 入口 + 三层命令 + 写操作门 `write_gate()`；内置 `META_ENDPOINTS`（9 个 GET）与 `META_WRITES`（buildMeta/modifyMeta）。
- `api.py`：HTTP 调用 + style 分支（`kapi`/`legacy`）。
- `auth.py`：苍穹增强型 Token（`POST /kapi/oauth2/getToken`），token 缓存到 `~/.ly/token-*.json`。
- `config.py` / `settings.py`：环境配置读写（同源 `~/.kd/config.json` 的 `env` 段）、写操作门模式。
- `envelope.py`：`ok()` / `fail()` JSON 信封输出。

**数据流（读）**：agent 调 `ly` → `cli` 解析 → `api.call(env, method, path)` → 苍穹 `{data,errorCode,message,status}` → `_unwrap()` 归一为信封。来源：`src/ly/cli.py:49-55`。

**数据流（写）**：非 GET 请求先过 `write_gate()`：默认 `confirm` 模式只返回**请求预览**，加 `--confirm` 才真正发 `api.call`；`free` 模式直接放行；`--dry-run` 任何模式只看预览。来源：`src/ly/cli.py:121-141`、`README.md:118-120`。

**架构决策（ADR）**：
- 0001：采用「CLI 核心 + 薄 SKILL.md 包装」而非 MCP（MCP 后置可选）。来源：`docs/adr/0001-cli-plus-skill-over-mcp.md`。
- 0002：环境配置与灵基「环境管理」同源（`~/.kd/config.json` 的 `env` 段，双写 camel/snake）。来源：`docs/adr/0002-shared-kd-config.md`。

**编码/目录约定**：
- 命名：`ly` 是唯一能力载体，SKILL 不承载逻辑只教调用。来源：`CONTEXT.md:10-13`。
- 凭证红线：密钥只存 `~/.kd/config.json`（仓库之外），**永不提交、永不进聊天、永不写入文档**；限流 30 次/分，密钥错误有锁定，禁止暴力重试。来源：`README.md:17-21,137-142`、`CONTEXT.md:52-55`、`skills/ly/SKILL.md:14-15`。
- 测试方式：项目本身**没有 pytest/unittest 测试目录**；评测闭环存在于 `kingdee-knowledge-kit/`（独立仓，`tests/verify_ksearch.py` + `data/eval` 金标 + `scripts/run_eval.py`）。`Lingya` 主仓里 `tools/verify_ksearch.py` 是**指向 kd 服务的回归脚本**，不是本仓单测。来源：`tools/verify_ksearch.py`、`kingdee-knowledge-kit/README.md:43,133`。主仓唯一「验收」靠 `ly doctor` + agent 端到端读回校验。来源：`CONTEXT.md:34-35`、`skills/ly/SKILL.md:22`。

---

## 3. 与金蝶星空对接现状

**对接方式 = 金蝶 OpenAPI（不是 kd CLI，也不是 kingdee-knowledge-kit）**。
- `ly` 直接打苍穹/星空服务端 OpenAPI；认证与报文由 `auth.py`/`api.py` 处理。来源：`src/ly/auth.py`、`src/ly/api.py`、`README.md:10`。
- `kd` / `kingdee-knowledge-kit` 只是「查官方知识」用，**完全不参与 ERP 读写**。来源：`kingdee-knowledge-kit/README.md:7`。

**当前只实现「苍穹（Cosmic，本地轻量环境）」路径，星空（K3 Cloud）尚未适配**：
- 苍穹：增强型 Token（`POST /kapi/oauth2/getToken`）+ `/kapi/v2/...` REST + `errorCode` 信封。已实现。来源：`src/ly/auth.py`、`docs/research/2026-09-07-xingkong-cloud-diff.md:22-28`。
- 星空公有云（K3 Cloud）：**v0.4 规划中，未实现**。调研结论是「分支逻辑」：K3 Cloud 用 `LoginBySign` 签名换有状态会话（`kdservice-sessionid` 头）+ `{"parameters":[...]}` 报文 + `Kingdee.BOS.WebApi.ServicesStub.*.common.kdsvc` 端点，与苍穹体系完全不同。来源：`docs/research/2026-09-07-xingkong-cloud-diff.md:1-17,88-145`（issue #7 调研）。
- 关键区分（坑）：星空旗舰版/AI 套件是**苍穹技术栈**，增强型 Token 很可能直接可用；只有「星空公有云 K3 Cloud」才需要新分支。动手前先确认客户产品线。来源：`docs/research/2026-09-07-xingkong-cloud-diff.md:12,145`。

**已覆盖的接口（苍穹，来源：`src/ly/cli.py:23-39`、`skills/ly/references/endpoints.md`）：**
- 认证：`/kapi/oauth2/getToken` / `verifyToken` / `withdrawToken`。
- 元数据只读（9 个 GET）：`getDevInfo` / `bizApps` / `queryForms` / `queryFormsByApp` / `getFormSchema` / `getEntityType` / `getFormMetadata` / `getFormConfig` / `getEntityFields`。
- 元数据写：`buildMeta`（新建表单）、`modifyMeta`（MetaOps 增删改字段/实体）；另有 `createPage`。
- 操作管理（经 api 透传，前缀 `/kapi/v2/devportal/ai-meta/operation/`）：`listOperationTypes`/`getOperationTypeSchema`/`addOperation`/`updateOperation`/`deleteOperation`/`listOperations`/`getOperation`。
- 插件管理（前缀 `/kapi/v2/devportal/ai-meta/plugin/`）：`registerPlugin`/`updatePlugin`/`deletePlugin`/`queryEditablePlugins`。
- **业务数据通道（save/submit/audit/query 等）尚未实现（v0.3 规划）**。苍穹业务 API 是「对象×操作」发布式路由 `/kapi/v2/{isv}/{appId}/{formId}/{serviceName}`，需先开放平台初始化 + 逐对象发布操作 API。来源：`docs/research/2026-09-07-kapi-data-endpoints.md:1-21,150-165`（issue #2 调研）。

---

## 4. 转换规则现状

**结论：主仓内「转换规则 / ConvertRule / 单据转换 / 转换插件」相关代码与文档目前为零。**

- 全仓（排除 `kingdee-knowledge-kit/` 子仓）检索 `转换规则`、`ConvertRule`、`convertRule`、`单据转换`、`转换插件`、`ConvertOp`：**零命中**。来源：`grep -rni` 结果（见来源清单末节）。
- 仅有的「规则」相关内容是**操作校验规则**（`ConditionValidation` / `GrpFieldsUniqueValidator` 等），属于元数据二开的操作校验，与「单据转换规则（下推转换）」不是同一概念。来源：`skills/ly/references/endpoints.md:17-21`、`docs/research/2026-09-07-ly-bom-unique-validation-case-study.md`。
- `ly meta` 当前没有 `convert-rule` / `convert` 子命令，`META_ENDPOINTS` / `META_WRITES` 也不含转换规则端点。来源：`src/ly/cli.py:23-39`。

> 含义：功能①「前台转换规则配置」是**全新绿地（greenfield）**：既无后端端点封装，也无前端/配置界面，需从「金蝶是否有转换规则的 OpenAPI」开始调研（BOS 开发平台的单据转换规则通常经设计器或特定服务配置，是否暴露到 `ai-meta` 或开放平台 API 未知——见第 7 节风险点）。

---

## 5. 自建单据与开发平台现状

**「自建单据」= 在开发平台（BOS 设计器）新建自定义业务对象/表单**。当前项目已有其 API 底座，但「测试」闭环尚未完整。

- `ly meta build-meta`：新建表单（设计器建模通道），走写操作门。来源：`src/ly/cli.py:36-38`、`skills/ly/SKILL.md:34`。
- `ly meta modify-meta`：已有表单增/删/改字段与实体（MetaOps）。来源：`src/ly/cli.py:36-38`、`skills/ly/SKILL.md:35`。
- 操作与校验全生命周期（增删改查操作、挂校验）已能经 `api` 透传 `ai-meta/operation/*` 完成。来源：`README.md:39`、`skills/ly/references/endpoints.md:43-45`。

**「开发平台 / BOS」在代码里的唯一落点**：
- `samples/BomCostRollupService.java`：一份**插件骨架样例**，注释里提到「开发平台(BOS设计器)搜到对应业务对象，看表单 FormId」「打开单据/基础资料的实体-字段列表，记字段标识」「现场数据库核对底层表」。这是 `kd.bos.*` Java 插件路线，依赖 JDK，是元数据二开之后的后续里程碑，不在 ly 首跑范围。来源：`samples/BomCostRollupService.java:13-21`、`CONTEXT.md:31-32`。
- `skills/ly/references/endpoints.md:12`：提到「在标准表单上做二开须先在开发平台 UI 手工创建扩展应用」（治理模式 `dev_governance_mode=centred` 下，开发商资源权限需管理员在开发者中心配置）。

**关键卡点（自建单据测试必经之地，来源：`skills/ly/references/endpoints.md:8-13`）：**
1. 扩展标准表单权限链：`form/action/extendPreCheck`（`formExtendable=true` 才允许扩展）→ `app/extend` 建扩展应用可能报 `NO_PERMISSION` → 直接对标准表单写操作报「表单不属于当前开发商，请扩展后再进行编辑」。
2. 卡点唯一解法：**管理员侧放开门户商资源权限，或在开发平台 UI 手工创建扩展应用**；之后 `extendForm → 改操作/规则` 全 API 可续。

**「测试」闭环的缺口**：
- 元数据层「改完读回验证」已可行（`getOperation`/`getEntityFields` 等）。来源：`skills/ly/references/endpoints.md:20`。
- 业务层「保存/提交/审核自建单据」**依赖尚未实现的 `ly data` 通道（v0.3）**。苍穹业务 API 需先开放平台初始化 + 逐对象发布操作 API，再 `POST /kapi/v2/{isv}/{appId}/{formId}/{serviceName}`。来源：`docs/research/2026-09-07-kapi-data-endpoints.md:71-92,150-165`。

> 含义：功能②「开发平台配置自建单据测试」= 用 `build-meta/modify-meta` 建/改自定义表单（已有）+ 用（待建的）`data` 通道做保存/提交/审核端到端测试（缺）。落地前提是 v0.3 数据通道，以及处理 BOS 扩展应用权限卡点。

---

## 6. 前台现状

**结论：主仓没有任何「前台 / frontend / Web UI」。** 项目目前是 **CLI + AI agent 驱动**，无浏览器界面、无前端框架。

- 检索 `前端`/`frontend`/`UI`/`web`：仅在 `README.md`「宿主落位」、交接文档（被 gitignore）、`kingdee-knowledge-kit` 子仓出现，主仓代码无前端。来源：`grep` 结果、`README.md:72`。
- 与用户交互的方式：**agent 在 shell 里执行 `ly` 命令**，读 JSON 信封；「说明书」是 `skills/ly/SKILL.md`，由 harness（灵基 build / ZCode / opencode）加载。来源：`CONTEXT.md:7-8`、`skills/ly/SKILL.md:8`。
- 所谓「前台」在现有语境下 = **AI agent 宿主侧的交互面**（agent 调用 `ly`），不是传统 Web 前端。来源：`CONTEXT.md:7`。

> 含义：功能①若叫「前台转换规则配置」，需先澄清「前台」指什么——(a) 新增 `ly meta convert-rule` 之类的 CLI 子命令 + SKILL 说明（最符合现有架构，零新依赖）；还是 (b) 真的要做一个 Web UI（当前完全没有技术栈基础，工作量与风险都大）。建议默认走 (a)，除非用户明确要 Web 界面。

---

## 7. 为两个新功能开发需要知道的约束与坑

### 功能① 前台转换规则配置
1. **绿地起点**：无任何转换规则代码/端点，需先确认金蝶是否暴露转换规则的 OpenAPI（ai-meta 或开放平台）。来源：第 4 节。
2. **「前台」语义待定**：现有项目无前端，建议落点为 `ly meta convert-rule` 子命令 + SKILL 文档，而非新建 Web UI。来源：第 6 节。
3. **沿用写操作门**：任何非 GET 写（创建/修改转换规则）必须走 `write_gate()`（confirm 预览 / `--confirm` 执行），与 build-meta/modify-meta 一致。来源：`src/ly/cli.py:121-141`。
4. **JSON 信封契约**：输出严格 `{ok,data}` / `{ok:false,error:{type,code,message,hint}}`，先判 `ok` 再取 `data`。来源：`README.md:110-116`。
5. **MSYS 路径坑**：Git Bash 下 `/kapi/...` 会被改写成 Windows 路径，`ly api` 已做还原，新增端点透传时注意。来源：`src/ly/cli.py:149-156`、`skills/ly/SKILL.md:17`。

### 功能② 开发平台配置自建单据测试
1. **依赖 v0.3 数据通道**：端到端测试（保存/提交/审核自建单据）必须等 `ly data`（业务 API 发布式路由）落地；当前只有元数据读写。来源：第 5 节、`docs/research/2026-09-07-kapi-data-endpoints.md:150-165`。
2. **BOS 扩展应用权限卡点**：标准表单二开必须先解决开发商资源权限 / 手工建扩展应用，否则 `app/extend` 与任何写操作报 `NO_PERMISSION` / 「请扩展后再编辑」。来源：`skills/ly/references/endpoints.md:8-13`。
3. **已实证的元数据写坑（务必复用）**：
   - `Lock` 属性禁止 `setProperties` 写布尔（会毒化 FieldAp，编译时 NPE「元数据保存失败: null」）。来源：`skills/ly/references/endpoints.md:13`。
   - `updateOperation` 是「属性平铺 + 整体替换」契约，改单条校验必须带全量数组。来源：`skills/ly/references/endpoints.md:20`。
   - `GrpFieldsUniqueValidator` 不支持条件过滤；基础资料字段引用必须用 `<key>.id`（如 `materialid.id`）；`IsCheckAllEntity` 是反义命名（true=忽略 DB 查重）。来源：`skills/ly/references/endpoints.md:19,21`、`docs/research/2026-09-07-ly-bom-unique-validation-case-study.md`。
   - 字段读回是 camelCase，写入 propertyNames 大小写不敏感；`Visible` 是状态串非布尔。来源：`skills/ly/references/endpoints.md:15-16`。
4. **「元数据保存失败: null」语义**：设计层已落库、运行时编译失败，一切以独立读回（`getProperties`/元数据库 `t_meta_entity`）为准。来源：`skills/ly/references/endpoints.md:14`。
5. **产品线性别**：若目标环境是星空公有云 K3 Cloud，需走 v0.4 新分支（LoginBySign 会话）；旗舰版/AI 套件苍穹系则现有 enhanced Token 基本可用。来源：第 3 节、`docs/research/2026-09-07-xingkong-cloud-diff.md`。

### 通用约束
- 凭证红线不可破：密钥只在 `~/.kd/config.json`（仓库外），新功能任何日志/文档不得落密钥。来源：`README.md:139`、`CONTEXT.md:54`。
- 主仓无单测体系，验收靠 `ly doctor` + agent 读回校验；若要补回归，参考 `kingdee-knowledge-kit` 的 `verify_ksearch.py` 模式（但那是独立仓）。来源：第 2 节。

---

## 8. 来源清单

### 本地文件（D:\01_Work\03_Develop\ingya 本地工作区）
- `README.md` — 项目定位、功能表、命令速查、JSON 契约、写操作门、路线图、安全红线。
- `CONTEXT.md` — 术语表（Harness/ly/SKILL/JSON 信封/环境/苍穹/星空/元数据二开/插件开发/端到端二开/扩展表单/坏引用探针）。
- `pyproject.toml` — 版本 v0.2.0、零依赖、入口 `ly.cli:main`。
- `src/ly/cli.py` — 命令三层、META_ENDPOINTS/META_WRITES、`write_gate()`、doctor。
- `src/ly/{api,auth,config,settings,envelope}.py` — HTTP/认证/配置/信封实现。
- `skills/ly/SKILL.md` — agent 说明书（铁律、命令、渐进加载）。
- `skills/ly/references/endpoints.md` — devportal ai-meta 端点全表 + 实测坑（扩展权限链、Lock、updateOperation、GrpFieldsUnique、IsCheckAllEntity 反义等）。
- `docs/adr/0001-cli-plus-skill-over-mcp.md` — CLI+Skill 优于 MCP。
- `docs/adr/0002-shared-kd-config.md` — 环境配置与灵基环境管理同源。
- `docs/research/2026-09-07-kapi-data-endpoints.md` — 业务数据通道（v0.3）端点选型（issue #2）。
- `docs/research/2026-09-07-xingkong-cloud-diff.md` — 星空 K3 Cloud 与苍穹差异（issue #7，分支逻辑结论）。
- `docs/research/2026-09-07-ly-bom-unique-validation-case-study.md` — BOM 唯一性校验实证（含 GrpFieldsUniqueValidator 反编译）。
- `docs/research-接口字段映射格式调研.md` — 跨系统字段映射格式（金蝶星空 WebAPI 段式结构参考）。
- `samples/BomCostRollupService.java` — BOS 插件骨架样例（开发平台/BOS设计器/FormId 注释）。
- `tools/verify_ksearch.py` — 指向 kd 服务的回归脚本（非本仓单测）。
- `.gitignore` — 排除 `kingdee-knowledge-kit/`、`灵基模型切换-交接文档*.md` 等。
- `kingdee-knowledge-kit/README.md`、`kingdee-knowledge-kit/CONTEXT.md` — 独立知识检索子仓说明（仅查文档，不参与 ERP 操作）。

### 检索实证
- `grep -rni "转换规则|ConvertRule|convertRule|单据转换|转换插件|ConvertOp"`（排除 `kingdee-knowledge-kit/`）→ **零命中**，证明功能①无现存代码/文档。
- `grep -rni "BOS|开发平台|自建单据"` → 仅命中 `samples/BomCostRollupService.java:17` 与 `skills/ly/references/endpoints.md:12,13`。
- `git ls-files` → 主仓跟踪：`docs/.gitignore/CONTEXT.md/LICENSE/README.md/pyproject.toml/skills/src/tools`；`kingdee-knowledge-kit/` 与 `灵基模型切换-交接文档*.md` **未入库**（gitignore）。

### GitHub 远程核对（WebFetch，URL：https://github.com/Drivpe/Lingya，抓取日期：2026-09-07）
- 远程 README 同样定位为「ly CLI + SKILL.md 跨 harness」、MIT、Python≥3.10、零依赖、JSON 信封、写操作门——与本地一致。
- **不一致点（需关注）**：远程 README 的路线图编号与本地不同——
  - 远程：`v0.2 数据查询/写操作`（业务 API）、`v0.3 与灵基 app-build 协同的元数据二开`、v0.4 星空适配。
  - 本地（fa37cc3 之后）：`v0.2.0 元数据二开写通道（已实现）`、`v0.3 业务数据通道`、`v0.4 星空适配`、`v0.5 扩展表单全流程`。
  - 即本地已把「元数据二开」提前到 v0.2.0 并标为已完成，远程 README 仍是旧顺序。**疑似远程滞后或 CDN 缓存**，建议推送前先 `git pull --rebase`/核对，避免覆盖。
- 远程最新提交（WebFetch 显示）：`d2bc823`（BOM 唯一性校验 issue #9 结案，2026-09-07）；本地 `git log` 最新为 `c107b39`（案例复盘补 v2 迭代），**本地领先远程若干提交**（`git status` 显示 `upstream is gone`，origin/main 引用已不存在）。
- 远程「View all files」列出的顶层与本地一致（docs/skills/src/tools + 根文件），**未列出** `kingdee-knowledge-kit/`、`samples/`、`灵基模型切换-交接文档*.md`、`CRM-OA-ERP接口集成手册.md`——与本地 gitignore/untracked 状态吻合（这些本就不在远程）。
- 远程 README 同样**未提及**转换规则/单据转换/自建单据/frontend/BOS 配置——确认 GitHub 侧也没有两功能的额外信息。

> 交接文档（`灵基模型切换-交接文档*.md`，gitignore 排除、本地有）经检索，**未提及**「转换规则配置」「自建单据测试」的规划或上下文（命中多为「测试会话/回归/路线」等无关语义）。两功能属全新规划，无历史交接上下文。
