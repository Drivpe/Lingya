# devportal ai-meta 端点全表(来源:灵基 app-build 技能 cosmic-meta-api)

GET 端点用 `ly meta <命令> --params '<JSON>'`;未包装的用 `ly api GET <path>`。
**已包装的写端点**:`ly meta build-meta --data '<JSON>'`(buildMeta,新建表单)、`ly meta modify-meta --data '<JSON>'`(modifyMeta,MetaOps 增删改)——走写操作门;请求体形状见灵基 app-build `cosmic-meta-api/apis/ai_meta.md`。

## ⚠️ 实测边界与坑(2026-09-07 本地苍穹验证)

- **禁止 setProperties 写 `Lock`(布尔)**:Lock 是布局层结构化属性,布尔写入会毒化该字段的 FieldAp——此后**该表单所有**元数据保存(含开发平台手工保存)在编译运行时元数据时 NPE(`ControlAp.getLockValue`),报"元数据保存失败: null"。设计文档仍会落库,但运行时元数据停更。**解毒**:`ly meta modify-meta` remove 该字段再 add 回来(重建布局控件),即恢复健康。
- **"元数据保存失败: null" 的语义**:设计层已保存、运行时层编译失败。一切以独立读回为准;批量写失败要拿 `getProperties` 读回逐项核对(部分属性可能已生效)。
- 字段读回属性名是 camelCase(mustInput/defValue);写入的 propertyNames 大小写不敏感。
- `Visible` 是按单据状态的可见性串(`init,new,edit,view,submit,audit`),不是布尔;状态级裁剪即"业务可见性"。
- 规则动作载荷:PascalCase(`ActionType`/`Fields`),且 `Fields` 必须是 `[{"_Type_":"FieldId","Id":"<字段key>"}]` 对象数组,传字符串报 ClassCastException。
- 操作校验(ConditionValidation)的表达式方言**不支持** `isNull()/isEmpty()`,空判写 `(x = null OR x = '')`;字段有 DefValue 时不可加"为空校验"(运行时永不为空)。

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
| getEntityFields | /kapi/v2/devportal/ai-meta/getEntityFields |

## 元数据操作(二开第二步)
| 端点 | 路径 |
|---|---|
| buildMeta | /kapi/v2/devportal/ai-meta/buildMeta |
| modifyMeta | /kapi/v2/devportal/ai-meta/modifyMeta |
| createPage | /kapi/v2/devportal/ai-meta/createPage |

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
