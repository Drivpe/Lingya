# 案例复盘 — BOM 维护「同一物料仅允许一张 BOM」唯一性校验(issue #9)

> 日期:2026-09-07 · 状态:**已结案**(运行时双组测试通过)
> 路线:零代码元数据二开,全程未写一行 Java
> 参数权威记录:`skills/ly/references/endpoints.md:19`(勿重新推导)

## TL;DR

在苍穹标准 BOM 维护表单上,仅用元数据 API(`ly` CLI)实现了「同一主物料只允许存在一张 BOM」的提交拦截。过程踩了三个反直觉陷阱,靠「坏引用探针 + DB ground truth」定位,最终经拦截组/对照组双组运行时测试闭环。**本案例是 ly 元数据二开路线的端到端实证**。

## 1. 需求与路线

需求:用户在 BOM 维护表单提交时,若该主物料已存在 BOM,则拦截并给出可识别提示。

路线决策:**零代码元数据二开**(写 Java 插件需要 JDK、编译、注册挂载,不可脚本化、不可重复)。元数据路线一切写入经 `ly api` 完成,可版本化、可重放、可被任何 harness 调用。

## 2. 最终落地形态

落点:扩展表单 `e8n4_pdm_mftbom_ext` → 实体 `pdm_mftbom` → 操作 Key `Submit` → validations 数组:

```json
{
  "_Type_": "GrpfieldsuniqueValidation",
  "enabled": true,
  "ruleType": "GroupFieldUnique",
  "fields": [ { "id": "materialid.id", "isv": "e8n4" } ],
  "isCheckAllEntity": false,
  "isCheckEmptyValue": true,
  "checkadata": false,
  "customPromp": "同一物料仅允许存在一张BOM(ly二开校验)"
}
```

**为什么能管到原表单**:操作/校验存于实体元数据表 `t_meta_entity`(fnumber=实体, fkey=操作key, fdata 为 camelCase JSON)。扩展表单对 Submit 的修改写进**共享实体的同一行**,运行时执行 submit 读的就是它——不依赖扩展表单合并,原 BOM 维护入口直接生效。

## 3. 三陷阱根因链(按踩坑顺序)

| # | 陷阱 | 反直觉之处 | 解法 |
|---|---|---|---|
| 1 | 裸写字段 key | 基础资料字段在字段树里被展开,叶子 id 是 `key.id` | 用 `materialid.id`(主物料.内码),标准表单 `createorg.id` 同款格式 |
| 2 | **`IsCheckAllEntity` 反义命名** | 字节码实证 `isIgnoreDB() = isCheckAllEntity`。**true = 忽略数据库、只查本次提交批次的内存数据**——单张提交永远静默放行 | 跨记录唯一必须 **`false`**(标准表单全部为 false) |
| 3 | 扩展表单处于停用状态 | 停用不影响落库与编译读回,但**不并入运行时元数据** | `enableDisable enabled=true` |

陷阱 2 是本案最深的坑:API 读回一度看不到 `IsCheckAllEntity` 键(疑似序列化省略默认值),导致「配置看起来对、运行时却放行」的错位。**结论:API 读回不是 ground truth,DB `t_meta_entity.fdata` 才是**。

## 4. 排障方法论(可复用)

1. **坏引用探针(运行时可证伪实验)**:故意写入不存在的字段引用 `nonexist_probe_field.id`。若运行时弹「配置错误,字段 X 已不存在,不能参与组合值唯一性校验」,即证明**校验器在执行、元数据已合并**——把「没生效」二分到「比对环节」。本案靠它定位到 `IsCheckAllEntity` 语义,而非靠静态推断硬猜。
2. **双读验证**:API 读回看结构,DB 直查看真实值;两者不一致时信 DB。
3. **页签缓存陷阱**:验证运行时前必须关闭并重开表单页签——旧页签加载的是旧元数据,会制造「改了没生效」的假象。

## 5. 三门槛验收

| 门槛 | 结果 |
|---|---|
| ① 元数据读回(API + DB 双读) | ✅ 通过 |
| ② 设计器字段选择器可见 | ✅ 运行时拦截成立即反证元数据已正确合并 |
| ③ 运行时双组验证 | ✅ **2026-09-07 通过**:拦截组(既有同物料 BOM-00000002~05 靶单)提交被拦、提示含「同一物料仅允许存在一张BOM(ly二开校验)」;对照组(全新物料)正常通过 |

测试数据 BOM-00000002~05 **保留**,作为后续 BOM 校验改动的回归靶子。

## 6. 附:「不动数据库可以实现吗?」

可以。本案**写入层全程未碰数据库**——所有变更经 `ly api POST /kapi/v2/devportal/ai-meta/operation/updateOperation` 完成。数据库仅承担可选的只读 ground truth 验证。若连只读查库也省去:结构核对用 `getOperation` 读回,生效性用坏引用探针在运行时证伪。唯一缺口是 `isCheckAllEntity` 在 API 层不可见,纯 API 路线只能靠运行时行为反推(被拦=false 正确;放行=true 需修正),查一次库是最快的定论手段。

## 7. 沉淀与遗留

- **沉淀**:参数语义与排障路径已固化到 `skills/ly/references/endpoints.md:19`;核查过程见 `docs/research/2026-09-07-ly-bom-unique-validation-runtime-check.md`。
- **遗留**:issue #9 在 GitHub 上待关(结案评论内容即本文档 §3/§5)。
- **红线回顾**:全程未把任何凭证写入文档/聊天/仓库;写操作走 confirm 门。

## 8. 迭代 v2:状态感知唯一(禁用不参与查重)

**新需求**:被禁用的 BOM 不应挡住同物料新建 BOM。

**侦察结论**:
- 反编译 `GrpFieldsUniqueValidator`(bos-mservice-operation-8.0.jar)证实其配置键仅 `fields/isCheckAllEntity/isCheckEmptyValue/isCheckMultilang/checkadata/customPromp/skipbillnovalidator`,DB 查重仅按「组字段相等+排除自身 id」构造过滤器——**不支持条件过滤**,无法直接表达「仅查启用记录」;
- 平台校验器清单(同包 29 类)无可零代码挂载的脚本校验;BOM 实体存在 `enable`(使用状态,BillStatusField)字段,不在设计器选择器排除类型中。

**方案**(纯元数据):组合唯一 `Fields=[materialid.id, enable]`——同物料同使用状态仅一张。新建 BOM 默认启用,故:同物料已有启用 BOM → 拦;旧 BOM 走禁用操作(不经 Submit,不受校验管辖)→ 禁用后同物料可重建。提示语同步更新为「同一物料仅允许存在一张启用BOM(ly二开校验)」。已知偏差:刻意新建「禁用态」新单时,同物料第二张会被拦(罕见路径)。

**实施中的新陷阱(重大)**:`updateOperation` 是**属性平铺契约**——body 传 `{"operation":{...}}` 包装报「至少需要指定一个要修改的属性」,须平铺 `{"formNumber","operationKey","validations":[...]}`;且 `validations` 为**整体替换语义**,改单条必须带全量数组——实测只传 1 条把 8 条标准校验全部冲掉,靠 getOperation 读回清点发现,再发全量 9 条恢复。两条实证均已沉淀 `skills/ly/references/endpoints.md`。

**待验收**:三场景运行时测试(①同物料+已有启用 BOM→拦,兼证 `isCheckAllEntity` 未被写坏;②靶物料启用 BOM 全禁用后新建同物料→过;③全新物料→过)。

## 来源索引

- 参数权威:`skills/ly/references/endpoints.md:19`(提交 e6f9ab0/e7e1311/d22c863)
- 前会话交接:`%TEMP%\handoff-ly-bom-unique-validation.md`
- 续查报告:`docs/research/2026-09-07-ly-bom-unique-validation-runtime-check.md`
- 反编译证据:`javap -p -c kd/bos/service/operation/validate/GrpFieldsUniqueValidator.class`(`isIgnoreDB() = isCheckAllEntity`)
- 运行时验证:用户人工双组测试(2026-09-07)
