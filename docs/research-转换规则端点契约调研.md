# 调研:苍穹单据转换(BOTP)转换规则端点契约(工单 #12 / C1)

- 日期:2026-09-07
- 环境:local-cosmic = http://127.0.0.1:8080/ierp(苍穹 8.0,本地安装 `C:\cosmic`)
- 方法:ai-meta 端点 GET 探针(19 个,间隔 ≥2s,全部只读)+ jar 反编译取证(javap 1.8 常量池)+ 灵基技能资产精读 + kd 知识库检索
- 铁律遵守:全部探针为 GET;文档不含任何 token/密钥

---

## 1. 结论摘要(TL;DR)

1. **ai-meta 族没有转换规则(BOTP)专用端点**。`convert-rule`、`convertrule`、`botp`、`pushdown`、`convert-rule/list`、`rule/list`、`query-forms-by-app` 全部 404("Cannot found OpenAPI(or disabled)")。但已实证可用的读端点组合足以支撑"规则元数据"侧: `bizApps` / `queryForms`(keyword)/ `getFormSchema`(formId)/ `getEntityFields`(formNumber)。【探针实证,见 §2】
2. **规则详情元数据可直接读**:转换规则本身就是一个动态表单实体 `botp_convertrule`(formId `0afd6ae6000003ac`,xkbotp 版 `xkbotp_convertrule` formId `40LA00DKXW2Q`)。`getEntityFields`/`getFormSchema` 已成功返回完整字段结构(含字段映射单据体 fieldmappolicy、分单/合并策略、业务规则策略、插件策略、单据类型映射等)【探针实证】。**但 ai-meta 系列只读"元数据",不返回规则行数据**。
3. **规则行数据(ruleId 列表)目前没有现成 OpenAPI**。ruleId 即 `T_BOTP_ConvertRule` 表主键【kd 社区答案 + jar 常量池 `ConvertDataService` 双证】。设计器列表页插件 `ConvertRuleListPlugin`(bos-botp-formplugin)就是对该实体做普通列表查询(select `id,sourceentitynumber.number,targetentitynumber.number`)。因此 ruleId 的获取路线为:浏览器抓包设计器列表请求(下一步)→ 复刻其通用列表查询端点;或经集成云/微服务侧获取。【§3/§4/§5】
4. **下推执行链契约已闭环**:灵基 `push-convert.md` 给出操作配置契约(push / pushandsave,parameter 必填 `targetBill`+`ruleId`,`@all`=运行时选择);jar 侧实证 `kd.bos.form.operate.botp.Push.AllRule = "@all"`;kd 官方知识库给出运行时等价调用——微服务 `invokeMicroService("bos","bos","ConvertService","pushAndSave", params)`,参数 `sourceEntityNumber/targetEntityNumber/ruleId/selectedRows[{pkv,eek,epkv}]`,与 jar 中 `ConvertServiceImpl.pushAndSave`/`PushArgs` 字段完全对上。【§4】
5. **设计器端点地图已从字节码恢复**:设计器【单据转换管理】页面是标准动态表单(`botp_convertop`、`botp_convertpath`、`xkbotp_convertrule` 等),UI → 服务端走苍穹通用表单服务;BOTP 专属服务端能力在 `ConvertMetaServiceHelper`(loadRules/loadAllConvertPaths/loadMeta/save/delete)与 `ConvertService` 微服务(push/pushAndSave/draw/beforeDraw 等)。这些是"能力地图",HTTP 形态需抓包确认。【§3】

---

## 2. ai-meta 探针实证表

前缀 `P = /kapi/v2/devportal/ai-meta`,环境 local-cosmic,全部 GET。返回信封为 `{"ok":bool,"data":...}` 或 `{"ok":false,"error":{"type","code","message","hint"}}`。

| # | 路径 | 参数 | 结果 | 关键返回摘录 |
|---|------|------|------|--------------|
| 1 | `P/convert-rule` | {} | 404 | `Cannot found OpenAPI(or disabled), url:/v2/devportal/ai-meta/convert-rule` |
| 2 | `P/convertrule` | {} | 404 | 同上(404) |
| 3 | `P/botp` | {} | 404 | 同上(404) |
| 4 | `P/pushdown` | {} | 404 | 同上(404) |
| 5 | `P/convert-rule/list` | {} | 404 | 同上(404) |
| 6 | `P/rule/list` | {} | 404 | 同上(404) |
| 7 | `P/bizApps` | `{"keyword":"botp"}` | **200** | 返回全部云/应用树(疑似 keyword 未生效)。定位到:**开发服务云(DEV, cloudId 83bfebc8000008ac)→ 单据转换管理: xkbotp appId=`36J2ZGF9FVZ5`;旧版 botp appId=`0a1f79d7000019ac`** |
| 8 | `P/queryForms` | `{"keyword":"botp"}` | **200** | 返回表单列表(含 formId/formNumber/appId)。含 `botp_logdb`(BOTP日志分库)等 |
| 9 | `P/query-forms-by-app` | `{"appId":"36J2ZGF9FVZ5"}` | 404 | 404(路由名不对) |
| 10 | `P/queryForms` | `{"appId":"36J2ZGF9FVZ5"}` | 200 | appId 参数未被过滤(返回全库前 200 条)——**queryForms 只认 keyword** |
| 11 | `P/queryForms` | `{"keyword":"convertrule"}` | **200** | 命中 5 个: `ct_botp_convertrule`、`botp_convertrulexml`、`botp_convertrulever`、`xkbotp_convertrule`、`botp_convertrule`(formId 见 §3.2) |
| 12 | `P/queryForms` | `{"keyword":"convert"}` | **200** | 命中 87 个,含 `botp_convertop`(单据转换弹窗)、`botp_convertpath`(转换路线列表)、`botp_convertresult`(下推结果)、`botp_newconvertpath`、`xkbotp_*` 全套 |
| 13 | `P/getFormSchema` | `{"formNumber":"botp_convertrule"}` | 400 | `getFormSchema.formId: 不能为空` → 该端点要 formId,不要 formNumber |
| 14 | `P/getEntityFields` | `{"formNumber":"botp_convertrule"}` | **200** | **返回转换规则详情全部字段**(header+所有单据体),见 §3.3 |
| 15 | `P/queryFormsByApp` | `{"appId":"36J2ZGF9FVZ5"}` | 400 | `appNumber 或 cloudNumber 至少传一个` → **端点存在**,参数名为 appNumber/cloudNumber |
| 16 | `P/getFormSchema` | `{"formId":"0afd6ae6000003ac"}` | **200** | 返回 botp_convertrule 完整 schemaText(见 §3.3) |
| 17 | `P/getEntityFields` | `{"formNumber":"botp_convertpath"}` | **200** | 转换路线列表:entryentity 字段 `fsourceentitynumber/fsourceentityname/ftargetentitynumber/ftargetentityname` |
| 18 | `P/queryFormsByApp` | `{"appNumber":"xkbotp"}` | 200 | `data: []` 空结果(疑为该端点只覆盖"设计态发布应用"或另有过滤,待抓包确认) |
| 19 | `P/queryFormsByApp` | `{"appNumber":"botp"}` | 200 | `data: []` 同上 |

**推论**:
- ai-meta 路由名 = 服务类公开方法名的 camelCase(方法 `queryFormsByApp` 存在于 `AIMetaBuilder`,探针 #15/#18/#19 证实路由存在)。`AIMetaBuilder`(bos-designer-ai-8.0.jar)公开方法全集:`getDevInfo / queryBizApps / buildMeta / createPage / queryForms / queryFormsByApp / getFormSchema / modifyMeta`;`MetaQueryApiController`(同 jar)另有 `getEntityFields / getFormPlugins / getPreviewUrl / getDesignerUrl / canAddField / canAddEntry / canAddFilterColumn / canAddToolbarItem` 等。**没有任何 BOTP/转换规则方法**。
- 404 文案 "Cannot found OpenAPI(or disabled)" 来自 OpenAPI 网关注册表校验(路由注册在网关侧数据库,不在 jar 内)——探针 404 不代表方法不存在,但 ai-meta 族服务类字节码里也确认无转换规则相关方法,双证成立。

### xkbotp / botp 关键表单 ID(探针 #11/#12 实测)

| formNumber | formName | formId | appId | modelType |
|---|---|---|---|---|
| botp_convertrule | 转换规则详情 | 0afd6ae6000003ac | 0a1f79d7000019ac (botp) | DynamicFormModel |
| xkbotp_convertrule | 转换规则详情 | 40LA00DKXW2Q | 36J2ZGF9FVZ5 (xkbotp) | DynamicFormModel |
| botp_convertpath | 转换路线列表 | 0ac36abc000001ac | 0a1f79d7000019ac | DynamicFormModel |
| botp_newconvertpath | 新建转换路线 | 0ae74ad5000003ac | 0a1f79d7000019ac | DynamicFormModel |
| botp_convertop | 单据转换(下推弹窗) | 5d1c305d000000ac | 0a1f79d7000019ac | DynamicFormModel |
| xkbotp_convertop | 单据转换(xkbotp 版) | 54EA4AYY1H+A | 36J2ZGF9FVZ5 | DynamicFormModel |
| botp_convertresult | 下推结果 | 50de79f0000001ac | 0a1f79d7000019ac | DynamicFormModel |
| xkbotp_convertresult | 下推结果(xkbotp 版) | 48S0J12YIFZ2 | 36J2ZGF9FVZ5 | DynamicFormModel |
| botp_convertrulever | 转换规则版本 | 2XF4/M45T/R6 | 0a1f79d7000019ac | BaseFormModel |
| botp_convertrulexml | 转换规则XML | 2ec23ff800000fac | 0a1f79d7000019ac | DynamicFormModel |
| botp_convertreport | 单据转换报告 | 5a344053000001ac | 0a1f79d7000019ac | DynamicFormModel |
| botp_convertprogress | 单据转换进度报告 | 0080VUAJ0P42 | 0a1f79d7000019ac | DynamicFormModel |
| botp_convertwatch | 单据转换监控 | 2MRCUS6C/LLJ | 0a1f79d7000019ac | BillFormModel |
| botp_convertlog | 转换规则日志 | 2XRXCZFE/QJR | 0a1f79d7000019ac | LogBillFormModel |
| botp_extclose_convertbase | 转换规则开闭 | 3M7WANJGNCI6 | 0a1f79d7000019ac | DynamicFormModel |
| ct_botp_convertrule | 数据协同规则详情 | 3HGKTEN+OHIF | 3J+CLX26ZXMO (ctsy) | DynamicFormModel |

---

## 3. jar 反编译端点/服务地图

方法:`unzip` 解包 + `javap -p -c` 提取常量池字符串(jar 位于 `C:\cosmic\mservice-cosmic\lib\bos\`)。苍穹的服务端 HTTP 形态是"网关路由 → 服务类方法",路由字符串在网关注册(数据库),jar 内可见的是**服务类与其方法/参数**,因此下表按"能力 → 类 → 方法"组织,并标注可确认的 URL。

### 3.1 BOTP 微服务(服务端能力地图)

**`bos-mservice-botp-8.0.jar` → `kd.bos.service.botp.ConvertServiceImpl`(实现 `ConvertService`)**

javap 实证方法(与 kd 官方文档 §4 的 `invokeMicroService("bos","bos","ConvertService","...")` 对应):

| 方法 | 入参 | 说明 |
|---|---|---|
| `push(String)` | PushArgs JSON | 下推(不自动保存) |
| `pushAndSave(String)` | PushArgs JSON | 下推并保存 |
| `beforeDraw(String)` / `draw(String)` | BeforeDrawArgs/DrawArgs JSON | 上查/选单 |
| `checkRunRuleCondition(String)` | PushArgs JSON | 校验规则启用条件(可用来验证 ruleId 可用性) |
| `getTargetOptionalOrgs(String)` | GetTargetOptionalOrgsArgs | 目标单可选组织 |
| `requirePushMutex / releasePushMutex` | — | 下推网控 |

**`bos-botp-business-8.0.jar` → `kd.bos.servicehelper.botp.ConvertServiceHelper`(Java 侧封装,签名同上)**;`kd.bos.servicehelper.botp.ConvertMetaServiceHelper`(规则元数据服务,规则读写的 Java 入口):

```
loadMeta(String ruleId, boolean) / batchLoadMeta(String[], boolean)
loadMetas(String sourceNumber, String targetNumber)   // 按源单+目标单取规则列表
loadRule(String ruleId) / loadRules(String, String)   // ConvertRuleElement
loadAllConvertPaths()                                  // 全部转换路线
loadConvertBills(String entityNumber, ConvertOpType)   // 某单可下推/上查的目标单清单
save(ConvertRuleMetadata) / saveDefaultStatus(...) / delete(String[] ruleIds)
loadLinkSet / loadMainTableDefine / loadTableDefine / loadSourceBills / loadTargetBills
```

**运行时参数对象** `bos-botp-core-8.0.jar → kd.bos.entity.botp.runtime.PushArgs / AbstractConvertServiceArgs`(javap 实证字段):

- AbstractConvertServiceArgs:`taskId, appId, sourceEntityNumber, targetEntityNumber, ruleId, buildConvReport, customParams(Map), jobTaskId, opInfo`
- PushArgs 增加:`selectedRows(List<ListSelectedRow>), defOrgId, currentOrgId, ruleIds(Set), hasRight, autoSave, showReport, wholeConvert, hidePushForm, countUserRule`

**下推操作插件** `bos-botp-business-8.0.jar → kd.bos.form.operate.botp.Push`:
- `public static final String AllRule = "@all"`(javap -constants 实证,与灵基 push-convert.md 的 `@all` 语义互相印证)
- 常量:`FORMID_CONVERTPROGRESS = "botp_convertprogress"`、`BOTP_TARGET_CLOSE = "botp_targetclose"`、操作选项参数 `wholeconvert / pushentityrow / showprogress / resultfrompopupreport`
- 另有 `Draw / TrackUp / TrackDown / TrackAll / PushDataExecuter / PushBigDataExecuter` 同包

### 3.2 设计器【单据转换管理】页面插件(bos-botp-formplugin-8.0.jar, kd.bos.designer.botp.*)

这些是标准表单插件(页面为 §2 的动态表单),字节码常量池实证其数据访问方式:

| 类 | 作用 | 常量池证据 |
|---|---|---|
| `ConvertRuleListPlugin` | 转换规则列表页插件 | 查询实体 `botp_convertrule`,select 字段串 `id,sourceentitynumber.number,targetentitynumber.number`,变量 `ruleId` |
| `ConvertPathEdit` | 转换路线列表 | 表单 `botp_convertrule`、`botp_crlist`、`botp_newconvertpath`,entryentity 字段 fsourceentitynumber/ftargetentitynumber… |
| `BillTypeMapTestEdit` | 单据类型映射测试 | 引用 `bos_billtype` |
| `RuleCacheHelper / GetRuleHelper / SetRuleHelper` | 规则读写助手 | `defRuleId`、`bizrulepolicy`、`convertsnapshot`、`fallowcrossentitymapping` 等 |
| `ConvertRuleStatusAsyncTask` | 启用/停用异步任务 | 表 `T_BOTP_ConvertRule_S`(状态表) |
| `NewConvertPathEdit / ConvertRuleEdit / ConvertRuleXmlEdit / WriteBackRule*` | 规则编辑/查看 XML/反写规则 | — |

**页面→服务端的 HTTP 形态**:上述插件运行在标准表单模型上,前端调用的是苍穹通用表单服务(列表查询/表单打开/操作执行/保存),无 BOTP 专用 HTTP 路由字节码。这正是下一步抓包要确认的通用端点(§5)。

### 3.3 转换规则实体元数据(getFormSchema 实测全文,节选自探针 #16)

主实体 `botp_convertrule`(转换规则详情)[MainEntity],关键字段:
- 主键 `id`;`fid`(唯一标识,TextField);`fname/fmulilangname`(名称)
- `fsourcebill`(源单,BasedataField→bos_objecttype)、`ftargetbill`(目标单)
- `fsourceentrykey/ftargetentrykey`(关联实体,必填)、`fsourcesubentrykey/ftargetsubentrykey`
- `fenabled`(启用)、`fdefault`(默认选用)、`fvisibled`(运行时可见)、`fdrawvisibled`(运行时选单可见)
- `fruncondition/frunconditiondesc`(规则启用条件)、`advanced_conditions`+`adv_filter`(高级条件)
- `fautosave`(下推自动保存)、`fbillpush`(整单下推)、`pushmutex`(网控)、`pushonetime`(不允许重复下推)、`flinkrecord`(记录关联关系)
- `createreport`(生成报告)、`convertsnapshot`(快照)、`sysstatus`(出厂状态)

单据体(entry):
- `fieldmappolicy` 字段映射:`ftargetfield/ftargetfieldname/fsourcefield/fsourcefieldname/ffieldformula(计算公式)/fconverttype(取值,必填)/fsumtype(合并,必填)/fdrawfilter/fdrawagainfilter/fclearsourcefield`
- `g_billcombo/g_entrycombo/g_subentrycombo` + `g_billentry/g_entry/g_subentry`(分单/行合并/子单据体合并依据)
- `bizrulepolicy` 业务规则策略:`br_enabled/br_bizruleitem(服务配置JSON)/br_bizruledesc/br_id`
- `pluginpolicy` 插件策略:`f_pl_enabled/f_pl_classname/f_pl_type/f_pl_plugin(插件JSON)`
- `billtypemappolicy` 单据类型映射:`sourcebilltype/targetbilltype/pushtype(下推类型,必填)`
- `attachmentpanelmappolicy` 附件面板映射

### 3.4 相关但次要的 HTTP 端点(jar 常量池实证)

- **ctbotp(多租户数据协同)OpenAPI**:`bos-ctbotp-core-8.0.jar → kd.bos.entity.ctbotp.constants.CtApiUrlEnum`,前缀 `/ierp/kapi/` + `/v2/ctsy/ctbotp/*`:`addLinks, addSyncRoute, buildEntityKeys, ctSave, deleteBills, deleteRules, getBillFields, getBillTreeNode, getEntityInfos, getSourceTreeNode, sync, syncRule, syncTenantPath, querySyncResult, updateSyncStatus` 等;另有 `/v2/ctsy/openapi/ctbotp/{getAllEntityObject, getBillData, getEntityObject, getTreeNode}`。(`CtBotpApiUtils` 显示跨租户调用走 `/api/login.do`+appToken 体系。)仅适用于"多租户协同"场景,不是本地规则管理通道,但证明 `deleteRules/syncRule` 这类规则操作在 ctbotp 有 OpenAPI 形态。
- `bos-botp-formplugin → BotpLogListPlugin` 引用 `/kapi/app/mc/GetDbInstanceListService`(日志分库查询用,次要)。
- BOTP 数据表(常量池 + kd 社区双证):`T_BOTP_ConvertRule`(规则主表)、`T_BOTP_ConvertRule_S`(状态)、`t_botp_log`、`t_botp_billtracker`、`t_botp_writebackrulever`、`t_botp_convert_watch` 等。

---

## 4. 下推执行链契约(灵基资产 + kd 来源)

### 4.1 操作配置契约(灵基 push-convert.md,全文精读)

来源:`C:\Users\Drivpe\.lingeebuild\config\builtin-skills\app-build\.locales\zh\skills\cosmic-meta-modifier\modules\operation\scenarios\push-convert.md`

- 操作类型三件套:`push`(下推)、`pushandsave`(下推并保存)、`statusconvert`(状态转换),均通过设计器元数据写接口 `addOperation` 配置到表单。
- **push/pushandsave 的 parameter 必填**:`targetBill`(目标单据编码)+ `ruleId`(转换规则ID);`ruleId = "@all"` 表示运行时弹规则选择(即"用户选择下推规则")。多目标可建多个 push 操作(operationKey 加后缀,如 `push_delivery`)。
- 通用配置:`confirmMsg`、`logEnable:true`;权限项推荐关联 `下推`(permissionItemId `4730fc9f000002ae`,来源 operation-params.md)。
- statusconvert 参数:`statusFieldId` + `value` + `isFullBillBillOperate:false`(原文为 `isFullBillOperate`)。
- 配套佐证:entity-operations.md §2.5 同样的 parameter 结构;operation-reference.md 的操作类型全集含 `push · pushandsave · statusconvert`。
- jar 互证:`Push.AllRule == "@all"`(bos-botp-business)——灵基文档的 `@all` 与平台实现一致。

### 4.2 运行时执行契约(kd 官方知识库)

来源:金蝶云社区官方知识库《集成服务调用苍穹BOTP的方法案例》 https://vip.kingdee.com/knowledge/261906779293195776 (kd 实测全文摘录)

方式一:集成云脚本函数 `IERP_BOTP(源单元数据编码, 目标单元数据编码, 源单ID[, map{proxy_user, ruleId}])`——只支持生成单张目标单。

方式二(**复杂场景推荐**):微服务调用,与 jar 侧 `ConvertServiceImpl.pushAndSave` 完全对应:

```js
var obj = {
  "sourceEntityNumber": "xxx",   // 必填,源单元数据编码
  "targetEntityNumber": "yyy",   // 必填,目标单元数据编码
  "buildConvReport": true,       // 选填,是否生成转换报告
  "ruleId": 1133313604662089728, // 选填,botp规则ID;不填自动找规则
  "selectedRows": [{"pkv": 1077487058685017088}] // 必填,源单ID,key 固定为 pkv
};
// 按分录下推时 selectedRows 追加: "eek":"billentry"(单据体标识), "epkv":分录主键
var result = invokeMicroService("bos", "bos", "ConvertService", "pushAndSave", FastJsonFormat(obj));
```

返回结构(节选):`{success, targetBillIds:[...], billReports:[{billId, billNo, ruleId, ruleName, failMessages, rowCount, failRowCount, success, fullSuccess, failMessage, rowInfo}], sourceEntityNumber, targetEntityNumber, ...}`。

要点:
- **ruleId 是数字型主键**(雪花 ID 形态,如 `1133313604662089728`),即 `T_BOTP_ConvertRule` 主键,不是 `fid` 字符串。
- ruleId 不填时引擎按 source/target 自动匹配(默认规则 fdefault)。
- 监控报告(kd《BOTP监控中心》 https://vip.kingdee.com/knowledge/381403466704901888 ):下推参数里会打印 `ruleId`、`appId`、`customParams`,报告入口【开发服务云】→【单据转换开发】→【监控报告】。
- 集成云还提供"集成方案转 API"(PULL/TRANSFER/PUSH/EXECUTE 四类,`POST /kapi/app/iscb/{api_number}`,kd knowledge 49142/49160)——不依赖转换规则的另一条数据流转通道,可作备选。

### 4.3 ruleId 从哪里取(现状小结)

| 途径 | 可行性 | 来源 |
|---|---|---|
| ai-meta 直接查规则列表 | ✗ 无此端点(§2 探针) | 探针实证 |
| ai-meta 读规则元数据(结构,非数据) | ✓ getFormSchema/getEntityFields | 探针 #14/#16/#17 |
| 设计器【单据转换管理】页面列表 | ✓(需抓包确认通用列表查询端点与载荷) | §3.2 ConvertRuleListPlugin 查询 botp_convertrule |
| 查询分析器/DB: `T_BOTP_ConvertRule` | ✓(社区官方答案,单表主键即 ruleId) | https://vip.kingdee.com/question/738043289542146048 采纳答案 "T_BOTP_ConvertRule" + jar ConvertDataService 常量 |
| 微服务 `ConvertMetaServiceHelper.loadRules(source,target)` | 服务端 Java/脚本侧可用 | jar javap + kd 案例同族 |

---

## 5. 待抓包确认清单(下一步浏览器抓包指引)

目标环境:打开 `http://127.0.0.1:8080/ierp` → 开发服务云 → 单据转换管理(xkbotp),DevTools Network 全程录屏,XHR/Fetch 过滤。

1. **规则列表页加载**【最高优先级】:打开"单据转换管理"首页/转换路线列表(`botp_convertpath`)与规则列表(`botp_crlist`/`botp_convertrule` 列表)。抓:列表查询端点(预计为通用表单列表查询,形如 `/ierp/kapi/...` 或 `service/controller` 调用)、请求体里的 formNumber/选择字段/分页参数。→ 这直接给出 CLI 批量列 ruleId 的通道。
2. **打开规则详情**(`xkbotp_convertrule`/`botp_convertrule`):抓表单打开(getFormShowParameter 类)与数据加载请求,确认按 ruleId 读规则全量的端点与返回结构。
3. **规则保存/启用停用**:新建或修改一条规则并保存;以及"启用/停用"按钮(ConvertRuleStatusAsyncTask)。抓写请求的端点与载荷(保存后可用于 CLI 只读校验对比)。
4. **运行时下推测试**:在任一业务单据列表勾选一条单据 → 点"下推"(botp_convertop 弹窗)→ 选择规则 → 确认。抓:弹窗数据加载(候选规则清单请求——即运行时 ruleId 列表的另一来源)、执行下推的操作请求(operationKey=push 的通用操作执行端点、operationId、载荷中的 ruleId/targetBill/pkIds)。
5. **下推结果页**(`botp_convertresult`):抓结果查询端点(供 CLI 判断下推成败)。
6. **对照验证**:`queryFormsByApp` 为什么对 appNumber=xkbotp/botp 返回空(抓包看设计器如何按应用列表单,纠正该端点参数)。
7. 顺手记录登录态机制(ly 已能透传,仅需确认抓包请求与 ly api 的 header 差异,注意不要把 token 写入文档)。

---

## 6. 补充实验(2026-09-07 深夜,C2 自动推进中):B 线通道读规则行的根因定位

C2 尝试复用 B 线「发布 query 操作 API」读 `botp_convertrule` 行数据,发现开放平台 query 运行时
对该实体一律 `java.lang.NullPointerException`(无论契约是全量、瘦列表还是最小三行;无论 id 必填/可选/带值)。
对照实验钉死根因:

| 实验 | 实体 | 模型类型 | DBRouteKey | 结果 |
|---|---|---|---|---|
| 对照 | `ly_test_bill_a1`(B 线已验) | BillEntityType | secd | query 正常 |
| 对照 | `bos_billtype`(标准资料,临时发布 `bos_billtype_query`,apiId `2563540873597943808`) | BasedataEntityType | basedata | query 正常(id=1 → 空行,不 NPE) |
| 目标 | `botp_convertrule` | **DynamicFormModel** | **sys.meta** | query 一律 NPE |

**结论:转换规则表单是 DynamicFormModel(纯 UI 壳,无物理表绑定)**——设计器列表页的数据是
`ConvertRuleListPlugin` 自己直查 `T_BOTP_ConvertRule`(§3.2),不是走表单模型;开放平台 query
运行时按表单模型找物理表映射,找不到即 NPE。**这断绝了"发布 query API 读规则行"的产品级通道**
(与契约写法无关)。

顺带修复(进入 main):
1. `data.py::_append_field` 空显示名回退参数名——此前 `botp_convertrule` 发布报
   `respentryentity 第 54 行缺少必填字段 'respdes'`(系统字段无 DisplayName 导致);
2. `ly data publish --query-id-optional`:query 契约 id 改可选(upsert 同 urlformat),
   对有物理表的实体兼得分页列全量能力;
3. `ly convert-rule` 子命令族(`publish-list`/`list`/`get`,src/ly/convert.py)已落地:
   publish-list 可用;list/get 在本通道被上述根因阻塞,代码保留,待新通道接上即可用。

#13(C2)的可行方向(需决策,见 issue 讨论):
- **A. 设计器抓包**复刻列表页请求(§5 清单;需用户配合,顺带把 ruleId 行数据通道一次拿全);
- **B. 服务端自定义操作插件**(Java,部署到本机 `C:\cosmic` 的 cus/):spec 已把「Java BOTP 插件路线」
  列为 out-of-scope,走此路需先改 spec;
- **C. 集成方案 PULL API**(`/kapi/app/iscb/{api_number}`,§4.2):集成方案配置本身要设计器 UI。

## 7. 来源清单
**探针实测(本机 local-cosmic,GET)**:§2 表 19 条,原始输出留存于临时目录 `probes.txt/probes2.txt/probes3.txt`。

**jar 反编译(本地 `C:\cosmic\mservice-cosmic\lib\bos\`,javap 1.8)**:
- bos-designer-ai-8.0.jar:`kd.bos.designer.ai.webapi.AIMetaBuilder`、`kd.bos.designer.ai.webapi.DevportalApiService`、`kd.bos.designer.form.MetaQueryApiController`
- bos-mservice-botp-8.0.jar:`kd.bos.service.botp.ConvertServiceImpl`、`kd.bos.service.botp.facade.OperateAutoPushFacade`
- bos-botp-business-8.0.jar:`kd.bos.servicehelper.botp.ConvertServiceHelper`、`kd.bos.servicehelper.botp.ConvertMetaServiceHelper`、`kd.bos.form.operate.botp.Push`(`AllRule="@all"`)
- bos-botp-core-8.0.jar:`kd.bos.entity.botp.runtime.PushArgs`、`AbstractConvertServiceArgs`
- bos-botp-formplugin-8.0.jar:`kd.bos.designer.botp.ConvertRuleListPlugin` 等 35 个插件类
- bos-botp-dao-8.0.jar:`ConvertDataService`(T_BOTP_ConvertRule 常量)等
- bos-ctbotp-core-8.0.jar:`kd.bos.entity.ctbotp.constants.CtApiUrlEnum`(`/v2/ctsy/ctbotp/*` 端点枚举)

**灵基技能资产**(`C:\Users\Drivpe\.lingeebuild\config\builtin-skills\app-build\.locales\zh\skills\`):
- `cosmic-meta-modifier\modules\operation\scenarios\push-convert.md`(全文)
- `cosmic-meta-modifier\modules\operation\entity-operations.md`(§2.5 push/pushandsave 参数)
- `cosmic-meta-modifier\modules\operation\operation-params.md`(下推权限项 4730fc9f000002ae)、`operation-reference.md`
- `cosmic-meta-api\contracts\cli\rule-domain.json`(注:该 rule 域为表单业务规则,与 BOTP 无关,已甄别)

**kd 知识库(金蝶云社区,kd CLI 检索/深读)**:
1. 《集成服务调用苍穹BOTP的方法案例》knowledge, https://vip.kingdee.com/knowledge/261906779293195776 —— IERP_BOTP / ConvertService.pushAndSave 微服务契约、返回结构
2. 《BOTP监控中心》knowledge, https://vip.kingdee.com/knowledge/381403466704901888 —— 下推参数含 ruleId、监控报告路径
3. 问答《单据转换路线是哪张表…》 https://vip.kingdee.com/question/738043289542146048 —— 采纳答案:T_BOTP_ConvertRule
4. 问答《拿到了源单分录id,如何调用BOTP的转换规则…》 https://vip.kingdee.com/question/293515438938584576 —— selectedRows 分录下推写法背景
5. 《OpenAPI整体介绍》knowledge, https://vip.kingdee.com/knowledge/226032339657008640 —— OpenAPI 注册/网关机制背景(404 文案出处)
6. 《集成方案API》knowledge, https://vip.kingdee.com/knowledge/49142 及《数据集成方案转API介绍》 https://vip.kingdee.com/knowledge/49160 —— PULL/TRANSFER/PUSH/EXECUTE 集成方案 API(`/kapi/app/iscb/{api_number}`)
