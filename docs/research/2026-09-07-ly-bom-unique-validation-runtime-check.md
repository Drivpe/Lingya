# ly 二开 BOM 唯一性校验(issue #9)— 交接续查与运行时前置核查

> 日期:2026-09-07
> 输入:`%TEMP%\handoff-ly-bom-unique-validation.md`(前会话交接)
> 关联沉淀:`skills/ly/references/endpoints.md:19`(根因链权威记录,勿重新推导)

## 1. 本次核查做了什么

按交接文档 P2 待办「探针还原未经独立确认」,通过 ly API 只读端点独立读回元数据核对。

**命令**(getOperation 为只读端点,虽是 POST 无副作用):

```bash
ly api POST /kapi/v2/devportal/ai-meta/operation/getOperation \
  --data '{"formNumber":"e8n4_pdm_mftbom_ext","operationKey":"Submit"}' --confirm
```

**读回结果**(来源:ly 实测输出,2026-09-07 15:10):

- ly 二开校验在位:`GrpfieldsuniqueValidation`,`Description="ly二开:同一物料仅允许一张BOM"`,`Enabled=true`,`RuleType=GroupFieldUnique`
- ✅ **探针已还原**:`Fields=[{"_Type_":"FieldId","Id":"materialid.id"}]`,无 `nonexist_probe_field` 残留 → P2 第一项闭环
- `CustomPromp="同一物料仅允许存在一张BOM(ly二开校验)"` 在位(拦截提示语识别依据)
- ⚠️ 读回 JSON **不含 `isCheckAllEntity` 键**——与交接文档 §7 记录一致(API 层不显示该参数),真实值以 DB `t_meta_entity`(fnumber=`pdm_mftbom`, fkey=`submit`)`fdata` 为准;交接文档记录 DB ground truth 已确认为 `false`(正确值),此项无需重验
- 标准校验未受影响:同操作仍含 `number + createorg.id` 编码唯一校验、状态校验等 8 项原生 validations

## 2. P1 答复:「不动数据库可以实现吗?」

**结论:可以。** 分两层(来源:交接文档 §1/§4 + 本次实测):

1. **写入层——本来就全程没动数据库。** 本次二开的所有写入均经 `ly api POST /kapi/v2/devportal/ai-meta/operation/updateOperation` 完成;数据库只承担**只读 ground truth 验证**(确认 `fdata` 落点与参数真实值)。
2. **验证层——如果连只读查库也想避免**,替代路径:
   - API `getOperation` 读回可确认校验结构在位(本次已演示);
   - **探针手法**(`endpoints.md:19` 沉淀):故意写坏引用 `nonexist_probe_field.id`,运行时若报「配置错误,字段 X 已不存在,不能参与组合值唯一性校验」即证明校验器在执行且元数据已合并——这是运行时可证伪实验,不需要查库。
   - **唯一缺口**:API 层看不到 `isCheckAllEntity`,无法从 API 判断该反义参数的真实值。纯 API 路线下只能靠运行时行为反推(单张提交放行 = 值为 true = 错;被拦 = 值为 false = 对)。查一次 DB 是最快的 ground truth,可选项而非必需项。

## 3. P0 运行时双组验证(唯一剩余硬门槛,需用户人工执行)

DB 已有 BOM-00000002/03/04/05 四张同物料测试单可当靶子:

1. **拦截组**:关闭 BOM 维护页签**重开**(旧页签加载旧元数据缓存)→ 新增 BOM,选那批同物料 → 保存 → 提交
   - 预期:被拦,提示含「同一物料仅允许存在一张BOM(ly二开校验)」或「字段值重复,请修改」
2. **对照组**:新增 BOM,选一个**从未用过**的第三种物料 → 提交
   - 预期:正常通过

两条同时成立才算闭环;任何一条不符,原样把现象记录后重新开排障循环(用运行时探针二分,别做纯静态推断)。

> **结果(同日 15:16 更新)**:双组测试已由用户执行并通过——拦截组被拦且提示正确,对照组正常放行。完整结案复盘见 `2026-09-07-ly-bom-unique-validation-case-study.md`。

## 4. P2 剩余

| 项 | 状态 |
|---|---|
| 探针还原核对 | ✅ 本次已确认(materialid.id 在位) |
| issue #9 结案 | ⏸ `gh` 未认证(实测 `gh auth status` 未登录),需 `gh auth login` 或走网页;结案内容=根因链(反义命名+字节码/DB 证据,见 endpoints.md:19) |
| 测试数据 BOM-00000002~05 处置 | 由用户定:留(后续回归靶子)或删(该物料已无法再提交新 BOM) |

## 5. 来源索引

- 交接文档:`C:\Users\Drivpe\AppData\Local\Temp\handoff-ly-bom-unique-validation.md`(§0 进度 / §1 已部署形态 / §2 根因链 / §3 待办)
- 根因链权威记录:`skills/ly/references/endpoints.md:19`(<key>.id 引用格式、IsCheckAllEntity 反义命名、探针手法)
- 命令契约:`skills/ly/SKILL.md`(JSON 信封、写操作门、凭证红线)
- 工作日志:`.workbuddy/memory/2026-09-07.md`
- 本次实测:ly getOperation 读回输出(本文件 §1)、`gh auth status`(未登录)
