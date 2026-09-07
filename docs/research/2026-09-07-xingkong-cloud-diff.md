# 调研:星空公有云(K3 Cloud)与本地苍穹在 ly 视角的差异

- 日期: 2026-09-07
- 工单: https://github.com/Drivpe/Lingya/issues/7 (Part of #1)
- 参考(只读): `src/ly/auth.py`、`src/ly/api.py`、`src/ly/config.py`
- 方法: kd CLI(金蝶官方知识库)+ 官方 SDK 源码交叉验证;文中所有示例均用占位符,无任何真实密钥。

---

## 结论(先行)

1. **"星空"要先分家**:本工单所说的星空公有云 = **金蝶云·星空(K3 Cloud,.NET 技术栈,kdsvc WebAPI 体系)**;而**星空旗舰版/金蝶AI套件是苍穹技术栈**,走 kapi + 第三方应用增强型 Token(与 ly 现有实现同构)。两条产品线的 API 体系**完全不同**,不能混为一谈。
2. **认证是根本性差异,不是参数差异**:K3 Cloud 没有 `/kapi/oauth2/getToken`,推荐方式是 **LoginBySign 签名登录**(SHA256 拼串签名)拿 `KDSVCSessionId` 会话,后续请求带 `kdservice-sessionid` 头;苍穹是**一步式 bearer token(2h 有效,可缓存)**。issue 里猜的"两步 getAppToken.do + login.do"**不适用于 K3 Cloud**——那是旗舰版/苍穹系的旧 AccessToken 认证方式。
3. **WebAPI 形状完全不同**:K3 Cloud 是 `{站点}/k3cloud/Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.{Save|Submit|Audit|ExecuteBillQuery|...}.common.kdsvc`,请求体是**位置参数数组 `{"parameters":[...]}`**,响应信封是 `{"Result":{"ResponseStatus":{"IsSuccess":...}}}`;苍穹是 `/kapi/...` REST + `{"errorCode":0,...}` 信封。ly 的 `_is_body_401`(HTTP 200 + errorCode 401)假设在 K3 Cloud 会失效。
4. **复用度判断:分支逻辑,不是薄适配层**。config.py 的 appId/app_id 别名归一、envelope.py 的 CLI 信封、HTTP 管道、token 缓存模式都可复用(估 60%+);但 auth 与报文映射必须各写一套。建议结构:**统一 api 门面 + 两套 auth(cangqiong / k3cloud)+ 一层响应归一化**,即"分支"而非"薄适配"——因为鉴权模型(无状态 token vs 有状态会话)无法用一个薄开关兼容。
5. 星空公有云环境获取:官网申请试用/购买后按 K1202 流程开通,站点地址和管理员账号邮件下发;appId/appSecret 在系统管理 → 第三方系统登录授权 中创建(获取应用ID 需跳转 open.kingdee.com 完成授权)。

---

## 1. 认证差异:苍穹 enhanced vs K3 Cloud kdsvc

### 1.1 ly 现状(苍穹 enhanced Token)

`src/ly/auth.py`:
- `POST {url}/kapi/oauth2/getToken`,JSON body:`{username, client_id, client_secret, accountId, language, nonce, timestamp}`
- 返回 `data.access_token`(2h),ly 缓存到 `~/.ly/token-*.json`
- 业务请求头:`accessToken` + 可选 `x-acgw-identity`;verifyToken/withdrawToken 配套
- 限流:1 分钟 30 次(拿 token 层面)

### 1.2 K3 Cloud 登录方式(官方知识,2023-08 版)

来源: [WebAPI登录接口介绍](https://vip.kingdee.com/knowledge/650369502764414208)、[WebAPI原生调用方式(不引用SDK)](https://vip.kingdee.com/knowledge/650355755563987456)

官方共列出 3 个登录接口(**推荐 LoginBySign,另外两个明示"不推荐、需整改"**,整改通知: https://vip.kingdee.com/school/detail/608228399106188288):

| 接口 | URL(POST) | parameters(位置参数) | 状态 |
|---|---|---|---|
| **LoginBySign** | `https://域名/K3Cloud/Kingdee.BOS.WebApi.ServicesStub.AuthService.LoginBySign.common.kdsvc` | `[账套ID, 用户名, 应用ID, 时间戳, 签名, 语言ID]` | **推荐** |
| ValidateUser | `...AuthService.ValidateUser.common.kdsvc` | `[账套ID, 用户名, 密码, 语言ID]` | 不推荐,明文,需整改 |
| LoginByAppSecret | `...AuthService.LoginByAppSecret.common.kdsvc` | `[账套ID, 用户名, 应用ID, 应用密钥, 语言ID]` | 不推荐,需整改 |

LoginBySign 签名算法(官方 C#/Java 示例):
1. 把 `账套ID、用户名、应用ID、应用密钥、时间戳(秒)` 放数组;
2. `StringComparer.Ordinal` / `Arrays.sort` 排序后**直接拼接**;
3. UTF-8 字节做 **SHA256**,输出小写 hex;
4. 旧版本(PT-146911、8.0.0.202205 之前)只支持 SHA1。

登录响应与会话(来自原生调用文档):
- 响应含 `LoginResultType`,`==1` 才算成功;
- 成功后取 `KDSVCSessionId`,后续所有业务请求头带 `kdservice-sessionid: <会话ID>`(或复用登录返回的 Cookie);
- **这是有状态会话,不是 bearer token**。没有官方的"有效期"字段,SDK(Java/Node 8.x)靠心跳检查 + 失效自动重登。

### 1.3 字段/端点对照(issue 的三个疑问逐一回答)

| 维度 | 苍穹 enhanced(ly 现状) | K3 Cloud 星空公有云 |
|---|---|---|
| 端点 | `POST /kapi/oauth2/getToken` | `POST /k3cloud/Kingdee.BOS.WebApi.ServicesStub.AuthService.LoginBySign.common.kdsvc` |
| 凭证字段 | `client_id`/`client_secret`/`username`/`accountId`/`nonce`/`timestamp` | `appId`/`appSecret`/`acctID(账套ID)`/`username`;**没有 nonce/timestamp JSON 字段**(时间戳进签名数组) |
| 获取方式 | 一步 POST 拿 access_token | 签名登录换会话;另有免登录的逐请求签名头(见 1.4) |
| 携带方式 | 请求头 `accessToken`(+ `x-acgw-identity`) | 请求头 `kdservice-sessionid`(或登录 Cookie) |
| 生命周期 | bearer token,2h,可缓存、可 verify/withdraw | 会话,无显式 TTL 字段,失效靠重登 |
| appId/appSecret/acctID? | 是(client_id/client_secret/accountId 同义) | 是,但叫 应用ID/应用密钥/账套ID(数据中心ID),且 appSecret 不直接进请求体而是参与签名 |

**getAppToken.do + login.do 两步流**:经查证,`/api/getAppToken.do`(grant_type=client_credentials, appId/appSecret/tenantid → app_token)+ `/api/login.do`(user/usertype/apptoken/tenantid/accountId → access_token)是**苍穹系(星空旗舰版/AI套件)的旧 AccessToken 认证方式**(示例: [旗舰版二开实战文章](https://vip.kingdee.com/article/847543161113812224));而且旗舰版第三方应用升级增强型 Token 后会**禁用 login.do 方式**(见 [第三方应用介绍](https://vip.kingdee.com/knowledge/549952532701564672) 变更记录 R202403.001:增强型 Token 一步拿 access_token+JWT,并禁用 login.do)。K3 Cloud 官方登录文档里没有这两个端点。**所以"星空=两步 getAppToken"的假设应放弃**。

**x-acgw-identity**:属苍穹系 API 网关身份标识(R202404.001 起 API 请求强制携带,第三方应用启用后自动颁发);K3 Cloud 无此头。

### 1.4 K3 Cloud 的"免登录"替代:逐请求签名头(Java/PHP SDK 8.x 风格)

若不想维护会话,官方 Java SDK 8.2.0 支持对**每个请求**生成签名头(实测自官方 SDK 镜像源码, [leoluonet/k3cloud-webapi-sdk](https://github.com/leoluonet/k3cloud-webapi-sdk),包名 `com.kingdee.bos.webapi.sdk`,与 Node 移植 [Xueyu334/k3cloud-api-nodejs](https://github.com/Xueyu334/k3cloud-api-nodejs) 交叉验证一致):

```
X-Api-ClientID: {appId 前缀(按 '_' 截取)}
X-Api-Auth-Version: 2.0
x-api-timestamp: {毫秒时间戳}
x-api-nonce: {同时间戳}
x-api-signheaders: X-Api-TimeStamp,X-Api-Nonce
X-Api-Signature: base64(hex(HMAC-SHA256("POST\n{urlencode路径}\n\nx-api-nonce:{n}\nx-api-timestamp:{t}\n", apiSecret)))
X-Kd-Appkey: {appId}
X-Kd-Appdata: base64("账套ID,用户名,语言ID,组织编码")
X-Kd-Signature: base64(hex(HMAC-SHA256(appId + appData, appSecret)))
```

PHP 官方 SDK(V8.2.0, [lizundao/k3cloud-webapi-sdk](https://github.com/lizundao/k3cloud-webapi-sdk) 体现)则是每个请求带 `X-KDApi-AcctID / X-KDApi-UserName / X-KDApi-AppID / X-KDApi-AppSec / X-KDApi-LCID / X-KDApi-OrgNum` 头。对 ly 来说,**逐请求签名头是有状态会话之外的第二条路线**(更接近 ly 无状态 token 的使用习惯,但算法复杂)。

---

## 2. WebAPI 差异

### 2.1 URL 形状

| | 苍穹 | K3 Cloud |
|---|---|---|
| 基址 | `{url}/kapi/...`(ly api.py 的 kapi style) | `{serverUrl}/k3cloud/Kingdee.BOS.WebApi.ServicesStub.{Service}.{Method}.common.kdsvc` |
| 查询 | `DynamicFormService`-风格 REST(kapi/v2 自定义 API) | `...DynamicFormService.ExecuteBillQuery.common.kdsvc` |
| 保存 | `/kapi/.../save` 类 | `...DynamicFormService.Save.common.kdsvc` |
| 提交/审核 | 同上 | `...Submit.common.kdsvc` / `...Audit.common.kdsvc` |

K3 Cloud 常用服务面(SDK 源码逐一核实,PHP/Java/Node 三方一致):`Save、BatchSave、Submit、Audit、UnAudit、Delete、View、Draft、Push、ExecuteBillQuery、GroupSave、GroupDelete、GroupSubmit、FlexSave、SendMsg、ExcuteOperation、SwitchOrg、QueryBusinessInfo、QueryGroupInfo、AttachmentUpLoad、WorkflowAudit、CancelAssign、GetSysReportData…`;认证面:`ValidateUser、LoginBySign、LoginByAppSecret、LoginBySimplePassport、ValidateUserByOrgNumber、Logout`。

### 2.2 报文形状

请求体(新版 SDK,8.x):**位置参数数组**

```json
{"parameters": ["<参数1>", "<参数2>", ...]}
```

- `ExecuteBillQuery`:parameters = `[{"FormId":"STK_Inventory","FieldKeys":"FID,FNumber","FilterString":"","OrderString":"","TopRowCount":0,"StartRow":0,"Limit":10}]`(第一个参数是查询 JSON 串)
- `Save`:parameters = `["<FormId>", {"Model":{...字段...}}, ...]`
- 旧版 ApiClient 报文(仍广泛流传,老环境可能要求):`{"format":1,"useragent":"ApiClient","rid":"...","parameters":[...],"timestamp":"...","v":"1.0"}` —— 帽子层已废弃,SDK 8.x 直接发 `{"parameters":[...]}` + 签名/会话头。

响应信封(K3 Cloud):

```json
{"Result":{"ResponseStatus":{"IsSuccess":true|false,
  "Errors":[{"FieldName":"","Message":"","DIndex":0}],
  "SuccessEntitys":[{"Id":"","Number":"","DIndex":0}],
  "SuccessMessages":[],"MsgCode":9},
  "Id":"...","Number":"..."}}
```

`ExecuteBillQuery` 的数据在 `Result.Result`(二维数组,按 FieldKeys 顺序)。

对照苍穹 kapi:`{"errorCode":0,"message":...,"data":...}`;ly `_is_body_401` 依赖的 "HTTP 200 + errorCode 401" 是苍穹模式,K3 Cloud 会话失效的表现不同(登录态丢时返回登录页 HTML/非 200,官方 SDK 用定时校验 + 自动重登兜底,Node SDK `sessionCheckIntervalMs` 默认 30s)。

### 2.3 权限前提

- 登录用户要有 WebAPI 权限:未启用子管理员时给账号挂 `administrator` 角色即可;启用子管理员走其授权流程(来源: https://vip.kingdee.com/question/832211644494653440)。用业务接口新增单据,该用户还要有对应单据的操作权限。

---

## 3. ly 代码逐文件:哪些假设会破

| 文件 | 假设 | K3 Cloud 下 | 判定 |
|---|---|---|---|
| `config.py` | appId/app_id、appSecret、accountId 别名归一 | 兼容好(appId/appSecret/acctID 概念一一对应;账套ID 建议增加 `acctId` 别名) | **可直接复用**,加 `kind` 字段区分 `cangqiong`/`k3cloud` |
| `auth.py` | 一步 getToken、2h bearer token、verify/withdraw | 全部不成立:LoginBySign 是签名换会话,无 verify/withdraw 对应物 | **不能复用 getToken;缓存模式(文件 + 过期检查)可借鉴**,改为会话缓存 + 失效重登 |
| `api.py` | `accessToken` 头 / legacy `access_token`+`api:true`;401/身内 401 重试 | 两种 style 都不适用,新增第三种 `kdsvc` style:`kdservice-sessionid` 头 + `{"parameters":[...]}` 报文;失效重试条件要按 `LoginResultType`/会话失效特征改写 | **call() 骨架可复用,style 分支与重试判定要改** |
| `envelope.py` | CLI 层 ok/error 信封 | 与远端信封无关 | **直接复用** |
| 响应归一(缺) | — | 需新增:`Result.ResponseStatus.IsSuccess → ok`,Errors → error 明细 | 新增一层薄归一化 |

**结论:分支逻辑。** 合理切分是:一个统一入口 `ly`,内部 `auth_cangqiong.py` / `auth_k3cloud.py` 两套鉴权 + `api.call` 按 `kind` 选 style + 响应归一层。硬塞进"薄适配层"会在"会话 vs token""信封差异""失效重试"三处渗漏,得不偿失。估复用度:config/envelope/HTTP 管道/缓存模式 ≈ 60%,auth 与 style 各自独立。

**若目标环境其实是旗舰版/AI套件(苍穹系)**:ly 现有增强型 Token 路径**大概率直接可用**(第三方应用 + 增强型 Token 同规范,仅多一个 x-acgw-identity 必带项),那是"薄适配"甚至零适配——先确认客户到底是哪条产品线再动手。

---

## 4. 星空公有云试用站点/凭证申请途径清单

| 途径 | 内容 | 来源 |
|---|---|---|
| 官网试用 | 金蝶云星空官网(kingdee.com)申请试用/体验中心在线体验;试用环境可用于 WebAPI 连通性验证 | https://vip.kingdee.com/question/470236877103033856 |
| 正式公有云环境 | 购买后按 **K1202 公有云环境开通申请** 流程开通,站点地址、管理员账号由邮件下发 | https://vip.kingdee.com/article/9261 (→ https://vip.kingdee.com/school/870) |
| 账套ID(acctID) | 管理员登录站点,WebAPI 测试页面可直接看数据中心 ID/账套ID | https://vip.kingdee.com/article/575368198254773248 |
| 应用ID/应用密钥 | 管理员 → 系统管理 → **第三方系统登录授权** → 新增 → "获取应用ID"跳转 **open.kingdee.com** 第三方系统登录授权页提交(填联系人/系统名等)→ 得授权码回填星空 → 自动生成应用ID;**查看应用密钥需二次验证密码**(首次需重置) | https://vip.kingdee.com/article/741305128644500736 、https://vip.kingdee.com/article/615853843376262656 |
| ISV/生态侧 | open.kingdee.com(星空开放平台)面向 ISV 的应用发布与授权;第三方直连租户站点仍是 WebAPI 主体用法 | https://open.kingdee.com/ |
| 旗舰版(苍穹系)试用许可 | 个人/伙伴可申请旗舰版试用许可(天梯/本地轻量环境),与 K3 Cloud 公有云不是一回事 | https://vip.kingdee.com/article/473791223610818304 |

凭证清单(K3 Cloud 联通最少集):`站点URL(serverUrl)`、`账套ID(acctID)`、`应用ID(appId)`、`应用密钥(appSecret)`、`用户名(username)`、`语言ID(lcid=2052)`;可选 `组织编码(orgNum)`。另需给该用户挂 WebAPI/单据操作权限。

---

## 5. 遗留待验证(需要真实环境)

1. KDSVCSessionId 实际有效期与失效时的确切响应特征(官方未给 TTL 文档;SDK 靠心跳/自动重登,需实测)。
2. 公有云站点的网络白名单/限流策略(官方对公网直连是否有额外网关要求,试用环境与正式环境是否一致)。
3. `{"parameters":[...]}` 新报文在客户实际版本上的兼容下限(极老版本可能仍要旧 ApiClient 帽子层)。
4. 客户产品线确认:K3 Cloud 还是旗舰版/AI套件——决定 ly 走新分支还是复用现有 enhanced 路径。

---

## 参考来源

- [WebAPI登录接口介绍(官方)](https://vip.kingdee.com/knowledge/650369502764414208) — LoginBySign/ValidateUser/LoginByAppSecret 报文与签名算法
- [WebAPI原生调用方式(不引用SDK,官方)](https://vip.kingdee.com/knowledge/650355755563987456) — LoginResultType/KDSVCSessionId/kdservice-sessionid
- [第三方系统登录授权(操作)](https://vip.kingdee.com/article/741305128644500736)、[获取第三方登录授权](https://vip.kingdee.com/article/615853843376262656) — appId/appSecret 申请与二次验证
- [第三方应用介绍(旗舰版/AI套件,官方)](https://vip.kingdee.com/knowledge/549952532701564672) — 增强型Token、x-acgw-identity、login.do 禁用
- [旗舰版二开实战( getAppToken.do/login.do 示例)](https://vip.kingdee.com/article/847543161113812224)
- 官方 SDK 8.2.0 源码镜像:[Java](https://github.com/leoluonet/k3cloud-webapi-sdk) / [PHP](https://github.com/lizundao/k3cloud-webapi-sdk) / [Node](https://github.com/Xueyu334/k3cloud-api-nodejs) — kdsvc URL 清单、X-Api-*/X-Kd-* 签名头、X-KDApi-* 头
- [公有云环境开通相关(9261)](https://vip.kingdee.com/article/9261)、[账套ID 获取](https://vip.kingdee.com/article/575368198254773248)、[WebAPI 权限问答](https://vip.kingdee.com/question/832211644494653440)
