# devportal ai-meta 端点全表(来源:灵基 app-build 技能 cosmic-meta-api)

GET 端点用 `ly meta <命令> --params '<JSON>'`;未包装的用 `ly api GET <path>`。

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
