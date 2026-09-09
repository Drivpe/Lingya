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

ly data precheck --form <表单编码>                    # 四项检查:表单存在/元数据可取/操作可查/开放平台在线
ly data publish --form <表单编码> --operations save,query,submit,audit [--confirm]  # 自动注册 v2 操作 API
ly data save --form <表单编码> --data '{"title":"x","qty":5}' [--confirm]  # 写业务数据(传 id=更新,不传=新增)
ly data query --form <表单编码> --id <单据id>          # 按 id 读回(发布契约必带 id+分页)
ly data operate --form <表单编码> --operation submit --id <单据id> [--confirm]  # 生命周期:submit/audit/unaudit/unsubmit/delete
ly api GET /kapi/v2/open/<表单编码>/query --params '{"id":"1","pageNo":"1","pageSize":"10"}'  # 任意已发布 API 兜底
ly api POST /kapi/v2/open/<表单编码>/save --data '{"data":{...}}' --confirm   # 原始调用(save 的 body 须包 data 层)

ly convert-rule list                                  # 转换路线列表(会话通道,首屏≤500;需 web 凭证)
ly convert-rule list --search "pur_order"             # 服务端过滤全量路线(不受首屏限制,2026-09-09 实测)
ly convert-rule get --id <ruleId>                     # 按 ruleId 读规则整行(OpenAPI 通道 botp_crlist)
ly convert-rule detail                                # 规则详情(默认第一行路线;解析规则树/字段值)
ly convert-rule detail --source <源单> --target <目标单>  # 直开指定规则详情(getConfig 自定义参数,2026-09-09 实测)
                                                      # rules[].rule_id 可直接用于 get --id
ly convert-rule enable --id <ruleId> --confirm        # 启用规则(OpenAPI;先 ly data publish --form botp_crlist --operations enable,disable --confirm)
ly convert-rule disable --id <ruleId> --confirm       # 停用规则(非幂等:重复同向报 603)

ly convert-rule new --source <源单> --target <目标单> --name <名称> [--set '{"k":"v"}'] --confirm   # 新建规则(ADDNEW+btnsave;路线已有规则时复用该行同 id;2026-09-09 实测)
ly convert-rule save --id <ruleId> --set '{"fname":"新名"}' --confirm   # 编辑既有规则字段(kingdee 规则被 st 锁不可写;同路线多规则时可能报 route_ambiguity)

ly api GET /kapi/v2/devportal/ai-meta/queryForms --params '{"keyword":"X"}'   # 任意端点兜底
ly config set write-mode free                       # 关闭写操作门(用户明确要求后才做)
```

环境选择:`-e <环境名>`;缺省取 `isDefault`。

## 会话通道(设计器页面)专用说明(2026-09-09 实测)

BOTP 转换规则没有 OpenAPI,ly 走**设计器通用表单服务**(Web 会话通道),需要独立凭证:

1. **先存凭证**:`ly auth web-add --user <手机号> --password <密码>`(存 `~/.kd/config.json` 的 webUser/webPassword;getPublicKey 只认手机号形态账号)。convert-rule list/detail 自动使用。
2. **list 首屏 500 条上限**是网格 page size(表单元数据配置),不是协议限制;全量检索用 `--search`(服务端对 1426 条缓存做 indexOf 匹配,源/目标编码与名称都会命中子串)。
3. **指定规则详情**用 `detail --source X --target Y`(getConfig params 里塞自定义参数 SourceBill/TargetBill,服务端 createFormShowParameter 兜底转 setCustomParam);**不要试图传网格选中态**——headless 通道不可传(entryRowClick 不写模型当前行,活体已证伪)。
4. **规则启停**用 `enable/disable --id`(OpenAPI 通道,不受设计器「其他开发商发布」锁定影响;重复同向操作报 603 状态前置错)。
5. **规则内容写入**(会话通道 `btnsave`,2026-09-09 破解并已落 CLI `convert-rule new/save`):`itemClick args=["btnsave",""]`(第二参空串必须存在)+ `postData=[{控件状态Map},[{"k":字段,"v":值}...],{子表单状态Map}]`——**三段必须是 [Map,List,Map],第三段给 `[]` 会 ArrayList→Map ClassCastException**(框架 FormController.postData,已实测踩坑)。kingdee 发布的原始规则字段被 `st` 状态锁死(「本规则由其他开发商发布,请勿直接改动;可以扩展一个新分支后修改」)——改 kingdee 规则必须先在设计器「扩展」新分支;本开发商自有规则可直接编辑。
6. 契约细节与逆向证据 → `docs/research-转换规则端点契约调研.md` §8 与 `docs/research/2026-09-09-batchInvokeAction-选中态与过滤契约.md`(§10 活体验证、§11 保存通道)。

## 业务数据通道配方(2026-09-07 实测)

自建单据要能被业务 API 读写,按序三步:

1. **建单时**:`build-meta` 的 artifact 实体**必须带 `tableName`(规则 `tk_{entityKey}`)**——缺了会得到占位表 `t_isv_xxx` 且无物理表,调用时报"关系不存在"。补救:`modify-meta` 对实体 `modify` tableName,平台会自动补建物理表。
2. **补操作**:骨架单可能缺标准操作(save/submit/audit 等)——`ly api POST /kapi/v2/devportal/ai-meta/operation/listOperations --data '{"formNumber":"..."}'` 查现有;缺就用 `addOperation`(必填 `formNumber/operationType/operationKey/operationName`)逐个挂,或建单时在 artifact 的 `operations` 里声明。挂完用 `ly data precheck` 确认操作列表。
3. **发布与调用**:`ly data publish --form X --operations save,query,submit,audit --confirm` → 每个操作得到一个 `apiId` + `urlformat /v2/open/<form>/<op>`;调用路径 = `/kapi/v2` + urlformat。**query 必带 `id` + `pageNo`/`pageSize`**(发布契约按 id 精确查);**save 的 body 必须包 `data` 层**(`{"data":{...业务字段}}`),`ly data save` 已自动包裹;候选键语义:传 id=更新(返回 type=Update),不传=新增;**未知字段会被服务端静默忽略**(不报错),字段名必须与实体属性精确一致;类型不匹配会返回结构化 error。
   - **两个已证实的坑(2026-09-09)**:① `--query-filter-fields` 发布的过滤参数**运行时不生效**(v2 open query 运行时只对 id 做 WHERE,实测确认)——要按业务字段过滤只能拉全量后客户端筛;② genV2ApiByMetaData 是整体替换语义,重发 publish 对 **save 等写操作会把 respentryentity 置空**——若该 urlformat 曾手工配置过返回参数会被清掉(ly 自家 query 的 resp 由 save_entries 重生成,不受此害),重发前先备份契约。
4. **生命周期与状态读回**:`ly data operate --operation submit|audit|unaudit|unsubmit|delete --id <id> --confirm`。操作 API 对状态迁移**宽松幂等**(重复同向操作也报成功);**状态读回用对向操作探针**:unaudit 成功即证处于已审核态、unsubmit 成功即证处于已提交态。id 不存在返回结构化 error(`未查找到需要xx的数据`)。注意:骨架单实体**没有 billno/billstatus 系统字段**(禁止 modify-meta 手工创建,buildMeta artifact 也不带),生命周期状态只存在于操作层,query 读不回状态字段——buildMeta 建单时若需完整单据语义,优先考虑在需求产物中声明(或接受操作探针方案)。

## C4 端到端下推配方(2026-09-09 深夜全链路实测)

自建单据 A 下推生成 B 的完整闭环,按序:

1. **建单**:`ly meta build-meta` 建 A、B 两个骨架单(实体 `tableName=tk_{entityKey}`,字段带 `columnName=fk_{isv}_{业务词}`,见上文配方)。
2. **建规则**:`ly convert-rule new --source A --target B --name <名> --confirm`——ADDNEW 页 **loadData 即落库骨架行**(fid 预分配,`isv_tag` 取会话身份),同路线已有规则时复用同 id。
3. **启用**:`ly convert-rule enable --id <ruleId> --confirm`(停用状态会报「无匹配规则」)。
4. **挂操作**:A 挂 `pushandsave`(后台自动整单下推并保存,entityOperation)与 `save`;B 挂 `save`——**下游单据没配保存操作会报「下推成功,但保存失败: 下游单据没有配置保存操作」**:
   `ly api POST /kapi/v2/devportal/ai-meta/operation/addOperation --data '{"formNumber":"<表单>","operationType":"pushandsave","operationKey":"pushandsave","operationName":"后台下推","parameter":{"targetBill":"<B编码>","ruleId":"<ruleId>"}}' --confirm`(pushandsave 参数 schema 经 getOperationTypeSchema 查得;save 同理 operationType=save)
5. **发布**:`ly data publish --form A --operations save,pushandsave --confirm`;`ly data publish --form B --operations save,query --confirm`。
6. **造源单**:`ly data save --form A --data '{"qty":"5"}' --confirm` → 得 A 单 id。
7. **下推**:`ly data operate --form A --operation pushandsave --id <A单id> --confirm`。
8. **断言**:`ly data query --form B --id <?>`——B 单 id 不在响应里,经物理表 `tk_ly_botp_b` 查 fid(本地环境可直连 PostgreSQL)或看 B 列表页。**骨架规则无字段映射行,qty 不会带过去**(字段映射增删改是独立缺口)。
9. 行为记录:重复下推**非幂等**,每次生成一条新 B 单。

## 元数据层验证配方(建→改→读回断言,2026-09-07 实测)

给 agent 的标准自建单据验证闭环,四步:

1. **建单**:`ly meta build-meta --data '<JSON>' --confirm`。请求体**平铺**(不要再包 `model`/`buildMeta` 外层),必填 `bizAppId` + `artifact`:
   ```json
   {"bizAppId":"<应用id>","artifact":{"requirementId":"<唯一id>","mode":"EXPERT","version":1,"status":"APPROVED","entities":[{"id":"e1","entityKey":"<表单标识>","displayName":"<名称>","type":"BillEntity","status":"CONFIRMED","tableName":"tk_<entityKey>","fields":[{"id":"f1","fieldKey":"<key>","columnName":"fk_<isv>_<业务词>","displayName":"<名称>","dataType":"TextField","status":"CONFIRMED"}]}]}}
   ```
   - `artifact` 是 `RequirementArtifact` 结构(见 references/endpoints.md 全表);`tableName` 规则 `tk_{entityKey}`、`columnName` 规则 `fk_{isv}_{业务词}`,缺失会被服务端逐条退回(按提示补齐即可)。
   - 返回 `entityResults[].success` 逐实体判定;报"表单已存在"说明之前已建过。
   - **应用权限**:`buildMeta` 只能落在当前开发商有资源权限的应用;用 `ly meta biz-apps` 找 `<isv>_*` 前缀的自属应用(isv 号见 `ly meta get-dev-info`)。
2. **改字段**:`ly meta modify-meta --data '<JSON>' --confirm`。请求体平铺 `{"formId":"<formId>","ops":[...]}`;op 结构 `{idempotencyKey, op:"add|modify|remove|move|bind|unbind|createModel", target:{treeType:"entity|form|mobform|moblist", elementType:"field|entity|...", locateBy:"key|id|path", value}, value:{fieldKey, fieldName, columnName, fieldType, ...}}`。add 字段时 `columnName` 必须显式给出。
3. **读回断言**:`ly meta entity-fields --params '{"formNumber":"<表单标识>"}'`(注意用 **formNumber** 不是 formId)与 `ly meta form-schema`,逐项核对 key/fieldType 与预期一致。
4. **失败处理**:所有失败已是结构化信封(`error.code` 如 `INVALID_ARTIFACT`/`NOT_ALLOWED`);`INVALID_ARTIFACT` 的 Jackson 报错会指明期望类型,照改即可;不要盲目重试同载荷。

## 渐进加载

按需读取 references,不要一次读全:
- 端点细节(元数据/操作/插件管理全表)→ `${LY_SKILL_DIR}/references/endpoints.md`
