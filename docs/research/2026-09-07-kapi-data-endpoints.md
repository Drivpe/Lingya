# 调研:苍穹业务数据读写 OpenAPI 端点选型(单据查询/保存/提交/审核/下推/报表)

- 日期:2026-09-07
- 对应 issue:Drivpe/Lingya#2(Part of #1)
- 问题:本地苍穹环境(http://127.0.0.1:8080/ierp,增强型 Token 认证已通)上,业务数据(单据/报表)的查询与写操作各走哪个 OpenAPI 端点、参数形状是什么?苍穹的 executeBillQuery 对应物是什么?报表有无独立通道?
- 方法:金蝶官方知识库(kd CLI 检索/读全文)一手来源优先;本地灵基资产 `cosmic-meta-api` 端点表交叉印证(确认 ai-meta 通道是元数据/设计器通道,与业务数据通道无关)。

---

## 结论(TL;DR)

1. **苍穹没有星空式的全局 `executeBillQuery` 标准 WebAPI**。对应物是「**查询操作 API**」:对每个业务对象(单据/基础资料)在【开放服务云 → OpenAPI → API 开发】零代码一键发布,系统自动生成路由。苍穹的「操作方式」是按对象预置的,查询也是其中一种,与 save/submit/audit/delete/push 同属一套体系。
2. **统一路由格式**:`/kapi/v2/{isv}/{appId}/{formId}/{serviceName}`,其中 `{isv}` 为开发商标识(金蝶标准接口为空)、`{appId}` 为业务对象所属应用编码、`{formId}` 为业务对象编码、`{serviceName}` 为发布时录入的 API 编码。查询可 GET(带分页参数)或 POST;写操作一律 POST。
3. **ly v0.2 的 data 命令封装建议**:不要把端点写死成"通用查询",而是封装成「按表单编码 + 操作方式生成/调用操作 API」的通道:
   - 查询:`GET/POST /ierp/kapi/v2/{isv}/{appNumber}/{entityNumber}/{queryApiCode}`(必带分页参数)
   - 保存:`POST .../{saveApiCode}`(候选键语义:传候选键=更新,不传=新增)
   - 提交/审核/反审核/删除/下推/撤销:`POST .../{submit|audit|unaudit|delete|push|undoApiCode}`(请求体参数经查询条件比较定位数据)
   - 报表:**无独立通用通道**(`listReportData` 之类的通用报表查询端点不存在);官方路线是「自定义 API(Java 插件/脚本)内部调报表 SDK(简单账表 `GetReportData`/移动报表 `GetListAndReportData`)」,绩效云合并报表另有专用 OpenAPI。
4. **鉴权/限流**:业务请求头必须带 `access_token`(增强型 Token 模式下只允许放 header,不允许 URL 传参);V6.0.1(R202410.001)起业务 API 还需 header 携带网关身份 `x-acgw-identity`。`getToken` 限频 1 分钟 30 次,token 有效期 2 小时。操作 API 可开「防止重复请求」(同参数 30 秒内仅一次)。

---

## 1. 通道全景:元数据 vs 业务数据

本地灵基 `cosmic-meta-api` 资产覆盖的 `/kapi/v2/uhyl/uhyl_aireqdecomp/ai-meta/*`、`/kapi/v2/devportal/ai-meta/*` 是 **AI 建模中心(设计器)通道**,管的是元数据建模(建表单/改字段/发布),不碰业务单据数据。

业务数据走的是另一套:**开放服务云 OpenAPI(开放平台)**,由 API 网关(API1.0 之外的新版 v2)承载,两种服务形态:

| 形态 | 说明 | 适用 |
|---|---|---|
| 操作 API(零代码) | 对业务对象的预置操作(加载/查询/保存/提交/审核/反审核/删除/撤销/下推/启用/禁用等)一键发布,出入参按界面配置自动生成契约 | 常规单据/基础资料读写(ly data 命令的主战场) |
| 自定义 API(Java 插件 / KingScript 脚本) | 出入参完全自定义 | 复杂场景:报表取数、分录级下推、合并下推等 |

来源:
- 操作API介绍(路由格式/操作方式/配置项):https://vip.kingdee.com/knowledge/555316763412680192
- OpenAPI调用流程(第三方应用/access_token/x-acgw-identity/统一响应契约):https://vip.kingdee.com/knowledge/543448746756000256
- OpenAPI(开放平台)整体介绍(操作API/自定义API/限流策略/防重复):https://vip.kingdee.com/knowledge/523450118653958400

## 2. 苍穹 executeBillQuery 的对应物:查询操作 API

- 星空的 `ExecuteBillQuery` 是一个全局标准 WebAPI;苍穹把"查询"也做成**每个业务对象独立发布的操作 API**,返回字段/查询条件/排序/分页全部在 API 定义里固化。
- 文档明确:**"无论是 GET 还是 POST,查询接口必须携带分页参数"**;建议查询条件选有索引的日期范围/单号/ID;避免子表属性作条件(全表关联)、名称 like(全表扫描)。
- 常量过滤可以把接口锁死在固定数据范围(如只允许查 A 组织);"在...中/不在...中" 比较方式要求参数类型为 Array。
- 可选配置项:`启用查询权限控制`(校验用户的组织权限与数据规则)、`返回动态对象`(返回 DynamicObject 序列化数据)、`返回多语言`、`是否脱敏`。

**入参形状**(GET 模式,以发布时配置为准):

```
GET /ierp/kapi/v2/{isv}/{appNumber}/{entityNumber}/{queryApiCode}
    ?pageNo=1&pageSize=100        # 分页必带(具体参数名以发布契约为准)
    &<请求参数>=<值>               # 查询条件比较变量
Headers:
    Content-Type: application/json
    access_token: <token>          # 增强 Token 模式:仅 header
    x-acgw-identity: <网关身份>     # V6.0.1+/R202410.001 起,第三方应用-身份凭证页可取
```

**返回形状**(平台统一契约,查询类同样遵守):

```json
{
  "status": true,
  "errorCode": "",
  "message": null,
  "data": { /* 发布时配置的返回参数,扁平化结构;GET 查询可含分页信息 */ }
}
```

来源:https://vip.kingdee.com/knowledge/555400185669328896 (查询操作API)、https://vip.kingdee.com/knowledge/555316763412680192 (操作API介绍,路由与配置项)。

### 落地注意(本地环境前置)

1. 本地苍穹需先执行【OpenAPI → 初始化】同步原厂标准 API 资源,再在【API 管理 → API 开发】为目标单据新建操作 API(选业务对象 + 操作方式 → 配置入参/查询条件/返回参数 → API 测试 → 发布)。
2. 第三方应用需通过「服务授权」(原厂标准 API 服务包)或「自建 API 授权」(项目自建 API)拿到调用范围授权。
3. 路由中 `{isv}`:金蝶标准接口为空;ISV 二开的接口带 ISV 标识(与本地灵基资产的 `uhyl` 前缀体系一致)。

来源:https://vip.kingdee.com/knowledge/543448746756000256 、https://vip.kingdee.com/knowledge/551054290966854912 (OpenAPI初始化介绍)、https://vip.kingdee.com/knowledge/548882576992034048 (一键同步原厂标准API接口)。

## 3. 写操作(Save/Submit/Audit/Unaudit/Delete/Push)端点与参数

全部是同一路由模式 `POST /ierp/kapi/v2/{isv}/{appNumber}/{entityNumber}/{serviceName}`,差异在「操作方式」与请求体语义:

| 操作 | 操作方式 | 请求体要点 | 文档 |
|---|---|---|---|
| 保存 | save | 按业务对象层级传扁平化字段;**候选键是更新/新增的开关**:命中候选键=更新,不传=新增;支持系统保存参数 | https://vip.kingdee.com/knowledge/555401045317338880 |
| 提交 | submit | 请求体参数 + 查询条件比较定位数据;支持批量 | https://vip.kingdee.com/knowledge/555412671055372288 |
| 审核 | audit | 同上;查询条件可批量审核(需谨慎) | https://vip.kingdee.com/knowledge/555420382836870912 |
| 反审核 | unaudit | 同上 | https://vip.kingdee.com/knowledge/555422413400062208 |
| 删除 | delete | 同上;可批量删除(需谨慎) | https://vip.kingdee.com/knowledge/555410900706709248 |
| 撤销 | undo(撤销) | 同上 | https://vip.kingdee.com/knowledge/555414025781956352 |
| 下推 | push | 同上;**仅支持整单下推**,分录下推/合并下推需自定义 API | https://vip.kingdee.com/knowledge/555423312944509184 |

**保存操作 API 的关键参数**(对 ly 封装最有价值):

- 系统参数:`importType`(new/override/overridenew,默认覆盖新增)、`firePropChanged`/`firePropChangedOnAdd`(值更新事件,>200 条分录开值更新有 10 倍性能损耗)、`forcedSubmit`(保存后自动提交)、`forcedAudit`(强制提交并审核)+ `WF=false`(跳过工作流直接审核)、`multiOps`(组合执行 `save,submit` / `save,submit,audit`)、`OverrideEntry`(更新时整体覆盖分录)、`mutex_ignoremodify`(忽略网络互斥)。
- 自定义参数:`rmStatusControl`(跳过已审核不可改校验)、`is_checkentryid`(更新时是否校验分录 id 存在)、`judgeKeyRepeatCheck`(内存中校验候选键唯一)。

**提交/审核/删除/下推的返回形状**(统一契约,带操作统计):

```json
{
  "status": true,
  "errorCode": "",
  "message": null,
  "data": {
    "filter": "",
    "result": [],
    "totalCount": "",   // 提交/审核/删除/下推/撤销类返回
    "failcount": "",
    "successcount": ""
  }
}
```

(保存类 `data` 为 `{result, failcount, successcount}`,无 filter/totalCount。)

**入参形状示例**(POST 写操作,以发布契约为准):

```
POST /ierp/kapi/v2/{isv}/{appNumber}/{entityNumber}/{apiCode}
Headers: Content-Type: application/json; access_token: <token>; x-acgw-identity: <id>
Body:
{
  "<候选键字段>": "...",                  // save: 候选键命中即更新
  "<字段1>": "...", "<分录标识>": [ ... ],
  "<查询条件比较变量>": "..."              // submit/audit/delete/push: 用于查询条件定位数据
}
```

## 4. 鉴权与限流(本地已通增强型 Token,补充约束)

- **增强型 Token 认证**(V6.0.1 新增):`POST /ierp/kapi/oauth2/getToken`,body:`client_id/client_secret/username/accountId/nonce(10分钟内不可重复)/timestamp(±5分钟)`,响应取 `data.access_token`(2 小时)+ 可选 `id_token`(JWT)。配套 `POST /kapi/oauth2/verifyToken`(验有效性与剩余时间)、`POST /kapi/oauth2/withdrawToken`(撤回);`refreshToken` 已于 V7.0.8 下架。
- **getToken 限频:1 分钟 30 次**;客户端应缓存 token,过期前用 verifyToken 探测再重取。
- **access_token 只允许放请求头**,不允许 URL 传参。
- **x-acgw-identity**:R202410.001(2024-10-30)起,业务 API 调用必须在 header(或 URL 参数)追加网关身份标识,取自【OpenAPI → 第三方应用 → 身份凭证】。
- 其余限流:开放平台提供「限流策略」配置(按 API/第三方应用维度);操作 API 可开「防止重复请求」(相同参数 30 秒内仅一次)。

来源:https://vip.kingdee.com/knowledge/537672007656380928 (认证方式-增强型Token认证)、https://vip.kingdee.com/knowledge/543448746756000256 (OpenAPI调用流程)。

## 5. 报表数据:没有独立的通用通道

结论:**不存在 `listReportData` 之类的通用报表取数 OpenAPI**。可选路线:

1. **自定义 API + 报表 SDK(官方推荐路线)**:写自定义 API(Java 插件或 KingScript),内部用 `ISysReportService` + `SysReportFilterModel` + `RptParams`(StartRow/EndRow 分页)调用简单账表 `GetReportData` / 移动报表 `GetListAndReportData`,把 DataTable 序列化为 JSON 返回。官方示例:https://vip.kingdee.com/article/337264184725122048 (WebAPI自定义接口获取报表数据);辅助:https://vip.kingdee.com/article/98475029272558848 (插件中获取分页账表数据)、https://vip.kingdee.com/article/273824919174636288 (分页账表封装自定义WebApi)。
2. **绩效云合并报表专用接口**:企业绩效云合并报表有专用 OpenAPI(依赖报表模板,「查询报表行数据」开发指南),属于领域专用通道,不通用。https://vip.kingdee.com/knowledge/284326664622818560
3. **数据集成方案转 API**(集成服务云):把数据集成方案发布为 API,适合批量数据同步而非报表展示。https://vip.kingdee.com/knowledge/49160 、https://vip.kingdee.com/knowledge/272107811331491840

**对 ly 的建议**:v0.2 报表需求出现前不封装报表通道;真要做,优先按路线 1 在苍穹侧写一个自定义 API,ly 侧只管调用(与操作 API 同样的鉴权/路由规范)。

## 6. ly v0.2 `data` 命令封装清单(结论落地)

| 子命令(建议) | 端点 | 方法 | 入参 | 返回 |
|---|---|---|---|---|
| `data query` | `/ierp/kapi/v2/{isv}/{app}/{entity}/{queryApiCode}` | GET(或 POST) | 分页参数(必)+ 查询条件变量;字段集由 API 定义固化 | `status/errorCode/message/data`(扁平化业务字段) |
| `data save` | `/ierp/kapi/v2/{isv}/{app}/{entity}/{saveApiCode}` | POST | 候选键 + 业务字段(扁平化,分录为数组);可选 importType/multiOps/forcedAudit 等 | `data.result/failcount/successcount` |
| `data submit` | `.../{submitApiCode}` | POST | 查询条件比较变量(定位单据) | `data.filter/result/totalCount/failcount/successcount` |
| `data audit` / `data unaudit` | `.../{auditApiCode|unauditApiCode}` | POST | 同提交 | 同提交 |
| `data delete` | `.../{deleteApiCode}` | POST | 同提交(危险:可批量,建议 ly 侧强制单号/ID 精确条件) | 同提交 |
| `data push` | `.../{pushApiCode}` | POST | 同提交(整单下推) | 同提交 |
| `data undo` | `.../{undoApiCode}` | POST | 同提交 | 同提交 |
| (报表) | 无通用端点;走自定义 API | POST | 自定义 | 自定义 |

公共请求头:`Content-Type: application/json`、`access_token`、`x-acgw-identity`(视版本)。

**关键设计含义**:苍穹的查询/写端点不是固定 URL,而是"每个对象 × 每个操作"各有一个发布产物。ly 侧应维护「表单编码 → 各操作 API 编码」的映射(可从本地元数据通道 ai-meta 的表单清单生成候选,再在苍穹 API 文档/管理页核对),而不是硬编码一个 executeBillQuery。

## 7. 来源清单

官方知识库(vip.kingdee.com,kd CLI 全文读取):
- 操作API介绍(路由 `/kapi/v2/{isv}/{appId}/{formId}/{serviceName}`):https://vip.kingdee.com/knowledge/555316763412680192
- OpenAPI调用流程:https://vip.kingdee.com/knowledge/543448746756000256
- OpenAPI(开放平台)整体介绍:https://vip.kingdee.com/knowledge/523450118653958400
- OpenAPI初始化介绍:https://vip.kingdee.com/knowledge/551054290966854912
- 一键同步原厂标准API接口:https://vip.kingdee.com/knowledge/548882576992034048
- 认证方式-增强型Token认证:https://vip.kingdee.com/knowledge/537672007656380928
- 查询操作API:https://vip.kingdee.com/knowledge/555400185669328896
- 保存操作API:https://vip.kingdee.com/knowledge/555401045317338880
- 提交操作API:https://vip.kingdee.com/knowledge/555412671055372288
- 审核操作API:https://vip.kingdee.com/knowledge/555420382836870912
- 反审核操作API:https://vip.kingdee.com/knowledge/555422413400062208
- 删除操作API:https://vip.kingdee.com/knowledge/555410900706709248
- 撤销操作API:https://vip.kingdee.com/knowledge/555414025781956352
- 下推操作API:https://vip.kingdee.com/knowledge/555423312944509184
- WebAPI自定义接口获取报表数据:https://vip.kingdee.com/article/337264184725122048
- 企业绩效云合并报表 OpenAPI:https://vip.kingdee.com/knowledge/284326664622818560
- 数据集成方案转API介绍:https://vip.kingdee.com/knowledge/49160
- 调用OpenAPI示例代码(Java/JS/Python HTTP 调用样例):https://vip.kingdee.com/knowledge/679403059352463872

本地资产(只读交叉印证):
- `C:\Users\Drivpe\.lingeebuild\config\builtin-skills\app-build\.locales\zh\skills\cosmic-meta-api\apis\ai_meta.md`(ai-meta 元数据通道端点表)
- `C:\Users\Drivpe\.lingeebuild\config\builtin-skills\app-build\.locales\zh\skills\cosmic-meta-api\auth.md`(accessToken 请求头约定,与本调研的 OpenAPI 头一致)

社区问答佐证:
- 苍穹第三方 API 调用认证体系(AccessToken/JWT/摘要):https://vip.kingdee.com/question/874940534342238976
