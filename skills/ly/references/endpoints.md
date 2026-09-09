# devportal ai-meta 端点全表(来源:灵基 app-build 技能 cosmic-meta-api)

GET 端点用 `ly meta <命令> --params '<JSON>'`;未包装的用 `ly api GET <path>`。
**已包装的写端点**:`ly meta build-meta --data '<JSON>'`(buildMeta,新建表单)、`ly meta modify-meta --data '<JSON>'`(modifyMeta,MetaOps 增删改)——走写操作门。

## 写端点请求体契约(2026-09-07 实测+反编译 bos-designer-ai-8.0.jar)

- **请求体一律平铺**,不要包 `model`/`buildMeta`/`modifyMeta` 外层——包了外层服务端反而读不到字段(报 model.artifact 不能为空 这类误导性校验错)。
- **buildMeta**:`{"bizAppId":"<appId>","artifact":<RequirementArtifact>}`。
  - `RequirementArtifact`(kd.bos.designer.ai.model.dto):`{requirementId, sourceDoc, parsedAt, mode(EXPERT/GUIDED/STANDARD), version, status(PARSING/REVIEW_PENDING/APPROVED/DEPLOYED), entities:[RequirementEntity], relations, rules, plugins, operations, propertySettings, pendingSummary, sessionSummary, toolbarButtons, entryToolbar}`。
  - `RequirementEntity`:`{id, entityKey, displayName, tableName, type(BillEntity/BaseEntity/FormEntity/ReportEntity/QueryEntity/EntryEntity/...), parentEntityId, description, status(CONFIRMED/PENDING/LOW_CONFIDENCE), confidence, fields:[RequirementField]}`。
  - `RequirementField`:`{id, fieldKey, columnName, displayName, dataType(TextField/IntegerField/DecimalField/DateField/ComboField/BasedataField/QtyField/...), mustInput, comboOptions, comboValues, basedataNumber, ...}`。
  - 服务端建模规则:`tableName` 必须 `tk_{entityKey}`;`columnName` 必须 `fk_{isv}_{业务词}`;缺一逐条退回(读 entityResults[].message 按提示补)。返回 `entityResults[].success` 逐实体判定;表单已存在则跳过。
  - 权限:只能落在当前开发商有资源权限的应用(自属 `<isv>_*` 应用;isv 号来自 getDevInfo)。
- **modifyMeta**:`{"formId":"<formId>","ops":[<MetaOp>]}`。
  - `MetaOp`(kd.bos.designer.ai.copilot.model):`{idempotencyKey, op(add/modify/remove/move/bind/unbind/createModel), target:MetaTarget, path, value, extra}`。
  - `MetaTarget`:`{treeType(entity/form/mobform/moblist), elementType(entity/field/toolbar/tab/control/button/listcolumn/...), locateBy(key/id/path), value, parentScope}`。
  - add field 的 `value`(fieldDef):`{fieldKey, fieldName, columnName(必填), fieldType(或 dataType), mustInput, maxLength/minLength/password(TextField), scale/precision/zeroShow(Decimal), defValue, comboItems/comboOptions(Combo), basedataNumber(Basedata), afterField?}`;BillNoField/BillStatusField 由 createModel 自动补。
  - 整体替换语义与读回校验同 updateOperation 家族;改后必须用 getEntityFields/getFormSchema 读回清点。

## ⚠️ 实测边界与坑(2026-09-07 本地苍穹验证)

- **扩展标准表单的权限链**(实测 pdm_mftbom/BOM维护):
  1. `form/action/extendPreCheck` 只读可用:`formExtendable=true` 表示平台允许扩展
  2. 扩展必须落在「扩展应用」里;`app/extend` 创建扩展应用报 **NO_PERMISSION「当前开发商没有该资源权限」**(治理模式 dev_governance_mode=centred 时,开发商资源权限需管理员在开发者中心配置)
  3. 直接对标准表单做任何写操作(modifyMeta/updateOperation 等)报 **「表单不属于当前开发商，请扩展后再进行编辑」**
  → 卡点唯一:管理员侧放开门户商资源权限,或在开发平台 UI 手工创建扩展应用;之后 extendForm→改操作/规则 全 API 可续
- **禁止 setProperties 写 `Lock`(布尔)**:Lock 是布局层结构化属性,布尔写入会毒化该字段的 FieldAp——此后**该表单所有**元数据保存(含开发平台手工保存)在编译运行时元数据时 NPE(`ControlAp.getLockValue`),报"元数据保存失败: null"。设计文档仍会落库,但运行时元数据停更。**解毒**:`ly meta modify-meta` remove 该字段再 add 回来(重建布局控件),即恢复健康。
- **"元数据保存失败: null" 的语义**:设计层已保存、运行时层编译失败。一切以独立读回为准;批量写失败要拿 `getProperties` 读回逐项核对(部分属性可能已生效)。
- 字段读回属性名是 camelCase(mustInput/defValue);写入的 propertyNames 大小写不敏感。
- `Visible` 是按单据状态的可见性串(`init,new,edit,view,submit,audit`),不是布尔;状态级裁剪即"业务可见性"。
- 规则动作载荷:PascalCase(`ActionType`/`Fields`),且 `Fields` 必须是 `[{"_Type_":"FieldId","Id":"<字段key>"}]` 对象数组,传字符串报 ClassCastException。
- 操作校验(ConditionValidation)的表达式方言**不支持** `isNull()/isEmpty()`,空判写 `(x = null OR x = '')`;字段有 DefValue 时不可加"为空校验"(运行时永不为空)。
- **GrpfieldsuniqueValidation 完整参数**(2026-09-07 实测+反编译+DB 验证):`Fields` 引用**基础资料字段必须用 `<key>.id`**(如 `materialid.id`=主物料.内码),裸 key 会致设计器报「找不到字段:%s,请删除。」——字段树把基础资料字段展开为子节点,叶子 id 是 `key.id`(标准表单的 `createorg.id` 同格式);普通字段直接用 key。**⚠️ `IsCheckAllEntity` 是反义命名:字节码实证 `isIgnoreDB() = isCheckAllEntity`——设 true = 忽略数据库、只查本次操作批次的内存数据(单张提交必放行);跨记录唯一必须设 `false`**(标准表单全是 false)。设计器选择器排除类型仅:MulBasedataField/DateRangeField/TimeRangeField/FlexField/MulComboField/BasedataPropField。`Checkadata`=暂存参与。**运行时排障利器**:元数据库 `t_meta_entity`(fnumber=实体,fkey=操作key,含 camelCase fdata)+ 数据表直查,是 API 之外的 ground truth;校验器引用解析失败会抛「配置错误,字段X已不存在」可用于探针。
- **updateOperation 是「属性平铺+整体替换」契约**(2026-09-07 实测,踩坑):body 形如 `{"formNumber":...,"operationKey":...,"validations":[...]}`,**不能**传 `{"operation":{...}}` 包装(报「至少需要指定一个要修改的属性」);且 `validations` 为**整体替换语义——改单条校验必须带全量数组**,只传一条会把其余校验全部冲掉(实测:9 条被冲剩 1 条,再发全量 9 条恢复)。改完必以 getOperation 读回清点条数。
- **GrpFieldsUniqueValidator 不支持条件过滤**(2026-09-07 字节码实证):配置键仅 `fields/isCheckAllEntity/isCheckEmptyValue/isCheckMultilang/checkadata/customPromp/skipbillnovalidator`,DB 查重仅按「组字段相等+排除自身 id」构造过滤器——**无法表达「仅查启用记录」**。状态感知唯一的零代码解法:把状态字段加进 `Fields` 组成组合唯一(如 `[materialid.id, enable]`,BillStatusField 不在设计器排除类型中,可直接用裸 key),语义=同物料同使用状态仅一张;禁用/启走独立操作不经 Submit,故「禁用旧 BOM→新建」可正常通过。

## 基础查询
| 端点 | 路径 |
|---|---|
| getDevInfo | /kapi/v2/devportal/ai-meta/getDevInfo |
| bizApps | /kapi/v2/devportal/ai-meta/bizApps |
| queryForms | /kapi/v2/devportal/ai-meta/queryForms(参数 keyword) |
| queryFormsByApp | /kapi/v2/devportal/ai-meta/queryFormsByApp(参数 appNumber/cloudNumber/keyword) |
| getFormSchema | /kapi/v2/devportal/ai-meta/getFormSchema |
| getEntityType | /kapi/v2/devportal/ai-meta/getEntityType |
| getFormMetadata | /kapi/v2/devportal/ai-meta/getFormMetadata |
| getFormConfig | /kapi/v2/devportal/ai-meta/getFormConfig |
| getEntityFields | /kapi/v2/devportal/ai-meta/getEntityFields(**参数 formNumber**,不是 formId) |

## 元数据操作(二开第二步)
| 端点 | 路径 |
|---|---|
| buildMeta | /kapi/v2/devportal/ai-meta/buildMeta |
| modifyMeta | /kapi/v2/devportal/ai-meta/modifyMeta |
| createPage | /kapi/v2/devportal/ai-meta/createPage |

## 业务数据通道(开放平台 v2,2026-09-07 实测)
| 端点 | 路径 | 说明 |
|---|---|---|
| getEntityOperations | POST /kapi/v2/open/openapi/getEntityOperations `{formNumber}` | 实体支持的操作列表;开放平台在线探针 |
| genV2ApiByMetaData | POST /kapi/v2/open/openapi_apilist/genV2ApiByMetaData `{"data":{...}}` | upsert by urlformat,**整体替换**语义(三大子表必须显式携带) |
| 业务调用 | `/kapi/v2` + 已发布 urlformat(如 /v2/open/{form}/{op}) | query 必带 id+pageNo/pageSize;save 候选键语义 |

ly 封装:`ly data precheck`(四项检查)与 `ly data publish`(元数据→自动构造 bodyentryentity/respentryentity/filter_entity→不变量校验→提交,规则 A~E 含基础资料拆分/多选基础资料/弹性域)。主表字段契约:`number={form}_{op}`、`urlformat=/v2/open/{form}/{op}`、`apiservicetype=0`、`version=2`、`status=C`(发布);子表行必填:body 段 `paramname/paramtype/must/body_level/bodyparamdes/example`,resp 段 `respparamname/respparamtype/resp_level/respdes/respexample`,filter 段 `filter_column/filter_compare`;paramname 全局唯一 ≤50。

## 操作管理
listOperationTypes / getOperationTypeSchema / addOperation / updateOperation / deleteOperation / listOperations / getOperation
路径前缀:/kapi/v2/devportal/ai-meta/operation/

## 插件管理
registerPlugin / updatePlugin / deletePlugin / queryEditablePlugins
路径前缀:/kapi/v2/devportal/ai-meta/plugin/(registerPlugin → .../plugin/register)

## 认证端点(ly auth 已封装)
- POST /kapi/oauth2/getToken(2h 有效,限流 30/min)
- POST /kapi/oauth2/verifyToken
- POST /kapi/oauth2/withdrawToken
- normal 两步(增强开关关闭时):/api/getAppToken.do + /api/login.do

## Web 会话通道(设计器通用表单服务,2026-09-09 实测;BOTP 转换规则等无 OpenAPI 页面的唯一通道)

凭证:`ly auth web-add --user <手机号> --password <密码>`(存 config webUser/webPassword;getPublicKey 的 accessKey 只认手机号形态)。契约全量见 `docs/research-转换规则端点契约调研.md` §8 与 `docs/research/2026-09-09-batchInvokeAction-选中态与过滤契约.md`。

| 端点 | 方法 | 契约要点 |
|---|---|---|
| /ierp/auth/queryParameters.do → getPublicKey.do → yzjlogin.do | POST | 登录三步;密码 RSA PKCS#1 v1.5(公钥来自 getPublicKey);错误 `{"errorcode":"login.loginBizException"}` |
| /ierp/form/getConfig.do | GET | params JSON `{"formId":"<formNumber>","flag":"<rand16>","f":"<rand16>",...extra}` → 响应头 `kd-csrf-token` + 响应体 `pageId`。**extra 键兜底转 setCustomParam**(服务端 createFormShowParameter 对非 bean 属性键逐一 setCustomParam)——传 `SourceBill/TargetBill` 可直开 botp_convertrule 指定规则详情(实证) |
| /ierp/form/batchInvokeAction.do | POST | body `pageId=&appId=bos&params=[{key,methodName,args,postData}]`;三头 client-start-time/kd-csrf-token/signature,signature=sha256hex(start+token+tail+params[:300])+tail,超 300 字节加 `__length__<n>`。分发按 params[].methodName,`ac` 仅标签 |

已实证动作(ly convert-rule 已封装):
- `loadData`(key="") → 首屏数据块(dataindex/rows/rowcount);botp_convertpath 全量 1426 条在服务端缓存,首屏 500 = 网格 page size,page-2+ 未破解。
- `search`(key="searchpath",**args=[["关键词"]] 必须包一层 List**,单串报「功能异常」)→ 服务端对全量缓存做源/目标编码+名称 indexOf 过滤,`u` 动作返回过滤后数据块。→ `ly convert-rule list --search`
- `itemClick`(key="tbar_main",args=["btnmodify","modify"],postData=[{treeviewap...},[]]) → showForm 新 pageId → botp_convertrule loadData → 规则详情(默认第一行)。→ `ly convert-rule detail`
- **网格选中态不可 headless 传输**(活体证伪):服务端 doModify 只读 `getEntryCurrentRowIndex("entryentity")`(0 基会话态);`entryRowClick`/`clickCell` 只派发事件不写模型当前行,前端 JS 也从不发 entryRowClick。指定规则一律走 getConfig 自定义参数路线。→ `ly convert-rule detail --source <src> --target <tgt>`

OpenAPI 侧配套:`botp_crlist` 是基础资料实体(T_BOTP_ConvertRule),已发布 query 契约(apiId 2563792031902084096,`--query-id-optional --query-filter-fields`)→ `ly convert-rule get --id <ruleId>`。注意:v2 open query 运行时只对 id 做 WHERE,业务字段过滤参数不生效(实验确认)。
