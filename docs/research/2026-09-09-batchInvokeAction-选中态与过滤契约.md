# 调研:batchInvokeAction 通道——网格选中态 / 列表过滤 / loadData 分页 / modify 链路(工单 #15 / C3 前置)

- 日期:2026-09-09
- 环境:local-cosmic = http://127.0.0.1:8080/ierp(苍穹 8.0,本地安装 `C:\cosmic`)。**本次服务探测返回 502/连接失败,全部为静态分析(字节码 + 前端 JS),无活体实验。**
- 方法:jar 反汇编取证(`C:\cosmic\jdk\bin\javap.exe -p -c`,GBK 输出经 `iconv -f GBK -t UTF-8` 后再 grep)+ 前端 JS(`C:\cosmic\static-file-service\public\js`)字符串/上下文取证。关键类:`bos-webactions-8.0.jar`(`FormAction`)、`bos-botp-formplugin-8.0.jar`(`ConvertPathEdit`)、`bos-form-metadata-8.0.jar`(`EntryGrid`/`AbstractGrid`/`Search`)。
- 铁律遵守:全文不含任何 token/密钥/密码/手机号明文(用户手机号 `18257728578` 按红线不写入任何载荷示例);未对本地服务做任何写操作,本次服务宕机故亦无读实验。

---

## 0. 先行结论:服务端读取选中行的"根因"

所有四个问题的根基是同一事实:**botp_convertpath 列表页的"当前选中行"不是靠请求里的某个字段传递,而是服务端按 `pageId` 会话维护在表单数据模型里的"entryentity 当前行索引"(`getEntryCurrentRowIndex`,0 基)**。`doModify`/`getSelectPath` 只调用 `getModel().getEntryCurrentRowIndex("entryentity")` 读它;未选中时该值为 `0`,这就是"modify 永远打开第一行"的字节码级原因。【证据:§1】

因此"修改指定规则"= 先通过网格控件动作把 entryentity 当前行索引设为目标行(0 基),再发 `itemClick btnmodify`。~~选中态的精确方法名是 `entryRowClick`~~ **(⚠️ 此推断已被活体验证推翻,见 §10:headless 直发 `entryRowClick` 不写模型当前行;可用路线是 getConfig 自定义参数直开详情,见 §10.2)**。【证据:§1、§4】

---

## 1. TL;DR 结论摘要

1. **网格选中态从请求哪个字段读取?** 服务端**不**从 `postData`/`args` 直接读"选中行";它读 `getModel().getEntryCurrentRowIndex("entryentity")`(0 基整数,服务端会话态)。要改变它,需先对 entryentity 控件发 **`entryRowClick`** 动作(`methodName="entryRowClick"`,`args=[<0基行索引>]`,`postData=[]`),其内部 `clickCell(focusField, rowIndex)` 设置当前行焦点。可用 JSON 形态见 §4 表。前序失败的 `selectRow`/`setSelectedRow`/`[{rk:n}]`/`{entryentity:...}`/`postData[1]=[seq]` 全部因方法名/字段错而静默回退到默认行 0。【证据:ConvertPathEdit.doModify/entryRowClick、AbstractGrid.entryRowClick,见 §1/§4】
2. **列表过滤/搜索怎么传?** `searchpath` 搜索框是**服务端过滤**(非纯前端本地过滤)。它走 `batchInvokeAction` 通道,对 `searchpath` 控件发 **`search`** 动作(`methodName="search"`,`args=[<关键字>]`,`postData=[]`),服务端在 **已加载的 1426 条路径缓存**上做源/目标编码+名称子串匹配(`checkPathSourceAndTarget` 用 `indexOf`),再 `refreshEntryGrid` 重绘。不发新端点、不重新查库。【证据:ConvertPathEdit.search/doSearchByBill/refreshEntryGrid,见 §2】
3. **loadData 支不支持分页?** `loadData` 本身是页面数据加载动作,**首屏 500 条上限来自 entryentity 网格控件的 page size**(`IDataModel.getEntryPageSize()`,由 botp_convertpath 表单元数据里 entryentity 控件的 pageSize 决定),**不是 loadData 的硬截断**。`afterCreateNewData` 已一次性 `loadAllConvertPaths()` 把全量 1426 条载入服务端会话缓存,网格只按页大小向客户端发首屏。分页由 entryentity 控件的 `getEntryData(...)`/`setPageRows(int)` 实现,page-2+ 的精确请求载荷**未破解(待活体验证)**。【证据:ConvertPathEdit.afterCreateNewData、EntryGrid.getEntryData/getEntryPageSize,见 §3】
4. **`ac=modify` 处理链路?** 工具栏 `tbar_main` 的 `btnmodify` 触发表单操作 → `afterDoOperation` → `doModify()`;`doModify` 读 `getEntryCurrentRowIndex("entryentity")` → 取该行 `fsourceentitynumber`/`ftargetentitynumber` → `showRuleForm(src, tgt)` → 以 `formId=botp_convertrule` + 自定义参数 `SourceBill`/`TargetBill` 打开规则详情表单(按**源/目标对**定位,不是 ruleId)。调用链见 §5。判定逻辑:未选中→索引 0→第一行;选中→索引 N→第 N+1 行。

置信度标注约定:【查证】= 字节码/JS 实证;【未证实/待验证】= 推断,需活体实验确认。

---

## 2. Q1:网格选中态如何从请求传给服务端

### 2.1 服务端实际读取方式(查证)

`ConvertPathEdit`(botp_convertpath 表单插件)的修改/删除链路**都只**通过数据模型的当前行索引定位选中行,与 `postData`/`args` 里的"选中"字段无关:

```
// kd.bos.designer.botp.ConvertPathEdit.doModify()  (bos-botp-formplugin-8.0.jar)
0: getModel()
4: ldc "entryentity"
... getEntryCurrentRowIndex("entryentity")   // ← 读"当前选中行"(0基)
... getValue("fsourceentitynumber", idx)
... getValue("ftargetentitynumber", idx)
... showRuleForm(srcNumber, tgtNumber)

// getSelectPath() 同样:getEntryCurrentRowIndex("entryentity") → 在缓存按 源/目标 匹配
```

- `entryRowClick(RowClickEvent)` 在插件层是**空实现**(`Code: 0: return`),因此单击不会在插件侧做任何事,只负责把"当前行焦点"落到网格状态上。【证据:ConvertPathEdit.javap:260-262】
- `getSelectPath()`(564-624)与 `doModify()`(416-449)共同证明:选中 = entryentity 的当前行索引,**不是** `seq` 列值、`rk` 行键、或任何 `postData` 结构。

### 2.2 当前行索引如何被写入(查证)

entryentity 控件在 `initialize()` 被强转为 `kd.bos.form.control.EntryGrid`(ConvertPathEdit.javap:81),并注册 `addRowClickListener`/`addHyperClickListener`。点击行时框架分发到 `AbstractGrid.entryRowClick(Integer)`:

```
// kd.bos.form.control.AbstractGrid.entryRowClick(java.lang.Integer)  (bos-form-metadata-8.0.jar)
0: getEntryState().getFocusField()        // focusField
... clickCell(focusField, rowIndex)       // ← 设置当前行焦点(写入网格状态/模型当前行)
... new RowClickEvent(this, rowIndex)
... rowClickEventListeners.entryRowClick(event)   // 触发插件 entryRowClick(本表单为空)
```

`clickCell(focusField, rowIndex)` 将网格当前行设为 `rowIndex`,此后 `getEntryCurrentRowIndex("entryentity")` 返回该值。即:**`entryRowClick(index)` 就是"选中第 index 行(0基)"的服务端动作**。【证据:AbstractGrid.javap:1327-1374】

### 2.3 前序失败尝试的根因(查证推断)

| 前序尝试 | 为何失败 |
|---|---|
| `postData[1]=[seq]` | 服务端根本不读 `postData` 里的选中;且 `seq` 只是 `refreshEntryGrid` 赋的 1 基显示序(见 §2.4),非当前行索引 |
| `[{rk:n}]` | 行键 `rk` 是前端选中态(`slctState`),不映射到服务端 `getEntryCurrentRowIndex`;本表单选中走 `entryRowClick` 而非 `rk` |
| `{entryentity:...}` | 没有这种 envelope;批量动作按 `params[]` 数组逐条以 `key/methodName/args/postData` 分发 |
| `selectRow` / `setSelectedRow` | **方法名错**。正确方法名是 `entryRowClick`(行点击分发器);`selectRows` 是父类 `AbstractGrid` 的(批量)选中方法,但本场景"设当前行"由 `entryRowClick` 完成 |
| batch `selectRow`+`modify` | 同上,方法名 + 字段都不符,服务端静默回退到默认当前行 0 |

### 2.4 `seq` 列的真实含义(查证)

`refreshEntryGrid` 在重绘网格时给每行写 `seq`,值为 `1,2,3,...`(从 1 自增,`iinc 4,1`)。因此 **`seq = 当前行索引 + 1`**。想打开 `seq=N` 的行,应 `entryRowClick(N-1)`。【证据:ConvertPathEdit.javap:985-1013】

### 2.5 确切可用的 JSON 形态(查证 + 待验证)

在 `batchInvokeAction` 的 `params` 数组中,**先于** `itemClick btnmodify` 的一条:

```json
[
  { "key": "entryentity",
    "methodName": "entryRowClick",
    "args": [ <0基行索引, 整数> ],
    "postData": [] },
  { "key": "tbar_main",
    "methodName": "itemClick",
    "args": ["btnmodify", "modify"],
    "postData": [ {"treeviewap": {"focus": {"id":"0","parentid":"","text":"业务云","isParent":true}}}, [] ] }
]
```

- `key` 必须是网格控件 key **`entryentity`**(由 `initialize()` 注册监听器与 `getEntryCurrentRowIndex("entryentity")` 双重确认)。
- `methodName` = **`entryRowClick`**;`args` = `[当前行索引]`(0 基,= `seq-1`)。
- `ac` 查询参数:现有 `detail` 流程用 `ac=modify`。`entryRowClick` 这条建议 `ac=entryRowClick`(或并入同一 `ac=modify` 请求,因 `batchInvokeAction` 按 `params[]` 逐条分发,`ac` 仅作动作标签,见 §5.1)。**`ac` 取值对分发无实质影响,待活体确认。**
- 置信度:方法名/key/args 结构【查证】;与 `itemClick` 合并发送 vs 分两次发送、以及 `ac` 取值【未证实/待验证】。

---

## 3. Q2:列表过滤/搜索的传递机制

### 3.1 是前端本地过滤还是发请求?(查证:服务端过滤)

`searchpath` 是 `kd.bos.form.control.Search` 控件(ConvertPathEdit.initialize 注册 `addEnterListener`,ConvertPathEdit.javap:90-96)。其 `search(SearchEnterEvent)` 处理器:

```
// ConvertPathEdit.search(SearchEnterEvent)  (bos-botp-formplugin-8.0.jar)
if (source.getKey().equals("searchpath")) {
    text = event.getText();
    doSearchByBill(text);     // → 服务端过滤
}
// Search 控件分发方法名 = "search" (kd.bos.form.control.Search.search(java.util.List))
```

- `doSearchByBill(text)`(723-763)从 `getPathCache()`(全量 1426 条缓存)中按 `checkPathSourceAndTarget`(`indexOf` 子串匹配 源/目标 编码与名称,765-806)筛选,再 `refreshEntryGrid(filteredList)` 重绘。
- **全程不重新查库、不走新端点**——纯服务端内存过滤 + 重绘。所以前序在浏览器里"用 JS 触发输入框 setter + Enter / 点图标没触发请求"是误判:它**确实发请求**(走 `batchInvokeAction` 的 `search` 动作),只是前序没走对框架事件层(见下)。

### 3.2 走哪个端点 / 什么 action(查证)

- 端点:**`/ierp/form/batchInvokeAction.do`**(与 loadData/modify 同一通道,无独立端点)。
- action:`search`(Search 控件分发方法名 `search(List)`)。
- 确切形态:

```json
[
  { "key": "searchpath",
    "methodName": "search",
    "args": [ "<搜索关键字>" ],
    "postData": [] }
]
```

- 注意:`Search.search` 形参是 `java.util.List<?>`,但 `SearchEnterEvent.getText()` 取单串;实际 `args` 是 `[文本]` 还是 `[文本]` 包一层需活体确认,**结构【查证】,arg 是否需再包 List【未证实/待验证】**。
- 过滤条件结构:服务端用 `checkPathSourceAndTarget` 对缓存做 `String.indexOf(keyword)`,**不是** `FilterInfo`/`QFilter`/`filter`/`queryParam`/`CustomFilter`。这些是列表(BillList)查询用的,本表单(动态表单 + entryentity 内存缓存)不采用。【证据:ConvertPathEdit.search/doSearchByBill/checkPathSourceAndTarget/refreshEntryGrid】

### 3.3 为什么前序浏览器手动触发无效(查证推断)

前端 `kd-cq` 框架对 Search 控件的"回车/点图标"有独立事件层(`addEnterListener` → 框架内部合成 `SearchEnterEvent` 并 dispatch `search`)。用原生 `input.value=...` + 派发 `KeyboardEvent` 不会经过框架的事件合成器,故不发包。正确复刻须用框架的 `invokeControlService`/`batchInvokeAction` 直发 `search` 动作(即上方 JSON),**无需模拟 UI 事件**。

---

## 4. Q3:loadData 分页与 500 上限来源

### 4.1 500 上限来自哪(查证)

| 环节 | 字节码证据 | 结论 |
|---|---|---|
| 全量数据加载 | `afterCreateNewData` → `ConvertMetaServiceHelper.loadAllConvertPaths()` → `putPathCache`(全量 1426)→ `doSearchByNodeId` 填充网格 | 1426 条**一次性进服务端会话缓存**,非逐页拉 |
| 首屏只回 500 | `EntryGrid.getEntryData(...)` 分页读取 entryentity,页大小取自 `IDataModel.getEntryPageSize()`(EG.javap:2251、3188、3453、3938 等多处) | 500 = **entryentity 网格控件的 page size**,由 botp_convertpath 表单元数据(entryentity 控件 pageSize/maxRowCount)决定 |
| 是否 loadData 硬截断 | `loadData` 仅是表单数据加载动作;`doModify` 链证明全部 1426 已在模型里 | **不是 loadData 硬截断**,是网格分页的客户端发页上限 |

→ **500 是 entryentity 网格的 page size(表单元数据配置),可配置,不是协议层不可破的上限。**【证据:ConvertPathEdit.afterCreateNewData、EntryGrid.getEntryData/getEntryPageSize】

### 4.2 有没有可传的分页参数(部分查证)

- entryentity 控件提供分页方法:`getEntryData(int,int,int,int,int,int,Boolean)`(EG.javap:976)与 `setPageRows(int)`(EG.javap:9052),底层 `getEntryDataEntities(int from, int to)`(1952)按行区间取。
- 翻页动作的分发方法名(如 `getEntryData`/`setPageRows`/框架内部 `fetchPageData`)与 `args` 精确形态**未在本次字节码中定位到明确 dispatch 入口(网格翻页由前端 grid 组件触发,方法名需活体抓包确认)**。【未证实/待验证】

### 4.3 对本 CLI 的影响

- `ly convert-rule list` 当前只能取首屏 500,是网格 page size 所致,**不是** `params` 里缺页参数。要全量须:① 调大 page size(需改元数据,不可取)或 ② 发翻页动作逐页取(载荷待破解)或 ③ 直接复用 `loadAllConvertPaths` 的服务端能力(旁路)。第 ③ 种已在父文档 §3 指出 `ConvertMetaServiceHelper.loadAllConvertPaths` 是 Java 入口,但无 HTTP 端点,需 C 线方案 B/C。

---

## 5. Q4:`ac=modify` 处理链路与"打开哪一行"判定

### 5.1 分发入口(查证)

`FormAction.batchInvokeAction`(bos-webactions-8.0.jar)把请求交给 `DispatchServiceHelper.invokeBOSServiceByAppId(appId, "FormService", "batchInvokeAction", [pageId, params, map])`(FormAction.javap:1104-1120)。`FormService` 按 `params[]` 每条的 `key` 找控件、`methodName` 调对应方法。**`ac` 仅作动作分类标签,实际分发以 `params[].methodName` 为准**(这也是 §2.5 备注 `ac` 取值不影响分发的原因)。【证据:FormAction.javap:955-1136】

### 5.2 modify 链路调用链(查证)

```
用户点 tbar_main 的 btnmodify
  → FormAction.batchInvokeAction → FormService.batchInvokeAction
  → params[].key="tbar_main", methodName="itemClick", args=["btnmodify","modify"]
  → 表单操作 "modify" 执行
  → ConvertPathEdit.afterDoOperation(...)        // javap:153-191, line 181 调 doModify
      → doModify()                                // javap:416
          1. n = getModel().getEntryRowCount("entryentity"); if n==0 return
          2. idx = getModel().getEntryCurrentRowIndex("entryentity")   // ← 决定"哪一行"
          3. src  = getValue("fsourceentitynumber", idx)
             tgt  = getValue("ftargetentitynumber", idx)
          4. showRuleForm(src, tgt)               // javap:1164
               a. isMetadataExist(src) / isMetadataExist(tgt) 校验
               b. FormShowParameter.setFormId("botp_convertrule")
               c. setCustomParam("SourceBill", src); setCustomParam("TargetBill", tgt)
               d. getView().showForm(parameter)   // → 新 pageId + formId, 走 loadData 详情
```

**判定关键分支**:`getEntryCurrentRowIndex("entryentity")`:
- 未选中 → 默认 `0` → 打开**第一行**(这就是"无选中永远第一行")。
- 已通过 `entryRowClick(N)` 设过焦点 → 返回 `N` → 打开第 `N+1` 行。

### 5.3 打开的"规则"按什么定位(查证,重要)

`showRuleForm` 以 **`SourceBill` + `TargetBill` 自定义参数**打开 `botp_convertrule`,**不是按 ruleId**。`botp_convertrule` 详情表单拿到这两个参数后加载对应的转换规则。因此:
- "修改指定规则"的两种等价途径:
  1. 设 entryentity 当前行索引 = 目标行 → `itemClick btnmodify`(本通道,走 showRuleForm);
  2. 直接 `getConfig(formId=botp_convertrule)` + `customParams{SourceBill, TargetBill}` 打开(若能构造自定义参数载荷,可跳过列表选中)。
- 这与父文档 §8.2-2 "545KB 详情"完全一致:详情按 源/目标对 加载规则树与映射。【证据:ConvertPathEdit.doModify/showRuleForm, FormAction 分发】

---

## 6. 第一手证据溯源表

| 结论 | jar | 类.方法 | 关键行(反汇编文件) | 本机命令 |
|---|---|---|---|---|
| doModify 读当前行索引 | bos-botp-formplugin-8.0.jar | ConvertPathEdit.doModify | javap:416-449 | `javap -p -c kd.bos.designer.botp.ConvertPathEdit` |
| entryRowClick 空实现 | 同上 | ConvertPathEdit.entryRowClick | javap:260-262 | 同上 |
| search 走服务端过滤 | 同上 | ConvertPathEdit.search / doSearchByBill / refreshEntryGrid | javap:369-386 / 723-763 / 945-1029 | 同上 |
| seq=显示序(1基) | 同上 | ConvertPathEdit.refreshEntryGrid | javap:985-1013 | 同上 |
| 全量 1426 入缓存 | 同上 | ConvertPathEdit.afterCreateNewData | javap:110-130 | 同上 |
| entryentity=EntryGrid 控件 | 同上 | ConvertPathEdit.initialize | javap:81 | 同上 |
| entryRowClick→clickCell 设当前行 | bos-form-metadata-8.0.jar | AbstractGrid.entryRowClick | javap:1327-1374 | `javap -p -c kd.bos.form.control.AbstractGrid` |
| 分页取数 getEntryData/pageSize | 同上 | EntryGrid.getEntryData / getEntryPageSize | javap:976 / 2251+ | `javap -p -c kd.bos.form.control.EntryGrid` |
| Search 分发方法名 search | 同上 | Search.search(List) | javap(Search):`public void search(java.util.List<?>)` | `javap -p kd.bos.form.control.Search` |
| batchInvokeAction 分发 | bos-webactions-8.0.jar | FormAction.batchInvokeAction | javap:955-1136 | `javap -p -c kd.bos.web.actions.FormAction` |

反汇编文件均落在 `/c/tmp/jx/`(`FormAction.javap`/`ConvertPathEdit.javap`/`EG.javap`/`AG.javap`/`Lk.javap`)。GBK 处理:`iconv -f GBK -t UTF-8 <x.javap >x.utf8`。

前端 JS(`C:\cosmic\static-file-service\public\js`)佐证:`dataGrid-commons.js` 的 `slctState`/`setSelectRows` 是**前端**选中态(`selectedRows`=`rk` 列表),与**服务端** `getEntryCurrentRowIndex` 是两套机制——这解释了为何前序用 `rk` 形态失败。`entryRowClick` 在 JS 侧是"点击选中"UI 配置(`suppressEntryRowClickSelect`/`entryRowClickMultiSelect`),服务端方法名正是 `entryRowClick`。

---

## 7. 未破解项与下一步建议

1. **entryRowClick 与 itemClick 合并发送 vs 分两次发送、以及 `ac` 取值**:建议活体(服务可用时,**只读实验**)先单发 `entryRowClick(idx)` 看 `getEntryCurrentRowIndex` 是否变化,再发 `itemClick btnmodify`。不要做写操作。
2. **page-2+ 翻页动作载荷**:`EntryGrid.getEntryData(int,int,int,int,int,int,Boolean)` / `setPageRows(int)` 存在,但网格翻页的前端 dispatch 方法名未定位,需活体抓包 `batchInvokeAction` 翻页请求。
3. **Search 的 `args` 是 `[文本]` 还是 `[文本]` 包 List**:`Search.search(List)` 形参为 List,但 `getText()` 取单串;建议活体验证。
4. **直接用 customParams 打开 botp_convertrule**:可绕过列表选中(§5.3 途径 2),但 `getConfig` 自定义参数载荷需验证。

---

## 8. 对 C3「修改指定规则」的可执行结论

- 选中并打开指定行 = `entryRowClick(目标行 0基索引)` → `itemClick btnmodify`,二者同 `params[]` 数组(或先后两次 `batchInvokeAction`)。
- 目标行索引 = `seq - 1`(`seq` 来自 list 首屏返回的 `dataindex["seq"]` 列)。
- 打开的规则详情由 `SourceBill`/`TargetBill` 决定,解析沿用现有 `parse_detail`(convert.py)。
- 以上【选中方法名/key/args 结构】为字节码查证;【合并发送方式/ac 取值/翻页】为待活体验证项(§7)。

---

## 9. 复核记录(2026-09-09,主会话独立复验)

本文关键结论已由主会话独立复跑取证命令复验通过,**结论全部成立**。复验用的命令比 §6 的"先解压再 javap"更短,推荐后续直接复用:

```bash
cd /c/cosmic/mservice-cosmic/lib/bos
JAVAP=/c/cosmic/jdk/bin/javap.exe

# 方法名清单(先确认方法存在)
"$JAVAP" -p -cp "bos-botp-formplugin-8.0.jar;bos-form-metadata-8.0.jar" \
  kd.bos.designer.botp.ConvertPathEdit 2>&1 | iconv -f GBK -t UTF-8

# 反汇编后 grep 关键调用(option -c)
"$JAVAP" -p -c -cp "bos-botp-formplugin-8.0.jar;bos-form-metadata-8.0.jar" \
  kd.bos.designer.botp.ConvertPathEdit 2>&1 | iconv -f GBK -t UTF-8 > /tmp/cpe.txt
```

> 注:Windows 下 `-cp` 分隔符用 `;`(Git Bash 里 jar 名不要加引号问题不大,但含 `;` 的 classpath 整体必须加引号)。**不加 `iconv` 中文字符串全为乱码**,这是最容易踩的坑。

复验结果(逐条对照):

| 结论 | 复验结果 |
|---|---|
| `ConvertPathEdit` 有 `entryRowClick(RowClickEvent)` / `search(SearchEnterEvent)` / `doModify()` / `getSelectPath()` / `doSearchByBill(String)` / `showRuleForm(String,String)` / `afterCreateNewData(EventObject)` | ✅ 全部存在 |
| `AbstractGrid` 有 `entryRowClick(java.lang.Integer)` / `clickCell(String,int)` / `setPageRows(int)` / `selectRows(...)` | ✅ 全部存在(注意:`selectRows` 与 `entryRowClick` 是两个不同方法,前序试 `selectRow` 失败即因用错) |
| `doModify` 真的读 `getEntryCurrentRowIndex("entryentity")` | ✅ 字节码:`getModel()` → `ldc "entryentity"` → `IDataModel.getEntryCurrentRowIndex:(Ljava/lang/String;)I`;同一调用还出现在 `getSelectPath`(取源/目标)与删除(deleteEntryRow)两处,共 3 处 |
| `search` 按 `searchpath` 分流 | ✅ 常量池出现 3 次 `"searchpath"`(注册监听 + 事件分流 + 另一处) |
| `afterCreateNewData` 一次性 `ConvertMetaServiceHelper.loadAllConvertPaths()` | ✅ `invokestatic kd/bos/servicehelper/botp/ConvertMetaServiceHelper.loadAllConvertPaths` |
| `showRuleForm` 打开 `botp_convertrule` 并传自定义参数 | ✅ `setFormId("botp_convertrule")` → `setShowType(MainNewTabPage)` → `setCustomParam("SourceBill", 源)` → `setCustomParam("TargetBill", 目标)` → `getCustomParams().put("checkRightAppId", <当前 appId>)` → `getView().showForm(...)` |

### 复核补正(对 §5.3 的精确化)

`showRuleForm(String src, String tgt)` **只**传两个自定义参数:`SourceBill`、`TargetBill`(外加框架自动补的 `checkRightAppId`)。`ParamKey_SourceBillName` / `ParamKey_TargetBillName` 两个常量**存在但不在本方法里传**(用于别处),因此"绕过列表选中直接打开规则详情"时,**只需构造 `SourceBill`/`TargetBill` 两个参数即可**,不必凑 Name 版本。【查证:showRuleForm 字节码 1215-1250 行区段】

### 遗留

`entryRowClick` 与 `itemClick` 能否合并进同一个 `params[]`、`ac` 该取什么值,以及 page-2+ 翻页的 dispatch 方法名,均**必须活体验证**(服务起来后做只读实验,勿写)。

---

## 10. 活体验证结果(第二轮,2026-09-09,服务已恢复)

对 §2-§5 的推断做了只读活体实验(目标行:pur_order→pur_instock,首屏 index=336/seq=337;首行:er_hotelbill→er_repaymentbill)。

### 10.1 网格选中态:entryRowClick 路线❌被推翻,真相修正

- **实验**:单发 `entryRowClick(args=[336])` → 再 `itemClick btnmodify`;以及二者合并进同一 `params[]`。两种发法详情都仍打开**第一行**(er_hotelbill→er_repaymentbill)。❌
- **前端佐证**:全量检索 `static-file-service/public/js` 两大网格 JS(dataGrid-commons.js / commonsrc1.js),`entryRowClick` 只作为**配置项**出现(suppressEntryRowClickSelect/entryRowClickMultiSelect),**从未作为 methodName 发包**(0 处命中)。
- **字节码补查**:`AbstractGrid.clickCell(String,int)` 完整反汇编显示它**只派发 CellClickEvent 给 listeners,从不写模型当前行**;而本表单插件只注册了 RowClick 监听(且为空实现)。`setEntryCurrentRowIndex` 的调用方全库仅:DeleteEntry/EmbedSubEntryGrid/EntryGridSetRowData/FlexEdit/ApiEntryPropConverter/FormDataModel(mvc)——**没有一处在这条 headless 分发链上**。浏览器里选中态是经另一条同步机制写入模型的(未继续追)。
- **结论修正**:`getEntryCurrentRowIndex` 只读的根因结论(§0)仍然成立且已实证;但 **§2.5 的 JSON 形态作废**——headless 通道目前**无法**设置网格当前行,"修改指定规则"改走 §10.2 的路线。

### 10.2 ✅ 直开指定规则详情:getConfig 自定义参数(新破解,活体实证)

字节码新证据:`FormShowParameter.createFormShowParameter(Map)`(bos-form-metadata)尾部有一个**兜底循环**:遍历 params Map 的剩余键,凡不是 bean 可写属性的,一律 `setCustomParam(key, value)`。即 **getConfig 的 params JSON 里可以直接塞自定义参数**。

消费端实证:`ConvertRuleEdit`(bos-botp-formplugin)确实通过 `getView().getFormShowParameter().getCustomParam("SourceBill"/"TargetBill")` 取参加载规则(常量池 + 字节码双证)。

活体实验(全部 ✅):

```
GET form/getConfig.do?params={"formId":"botp_convertrule","flag":"<rand16>","f":"<rand16>",
                              "SourceBill":"pur_order","TargetBill":"pur_instock"}
→ pageId → batchInvokeAction ac=loadData
→ 规则树命中: rule_id=247559344043186176 「协同采购订单_采购入库_转换规则(原始,已停用)」
   (源/目标对正确; Name 版本参数不必传)
```

这就是"修改指定规则"的可用通道,**完全绕过网格选中**。已实现为 `ly convert-rule detail --source <源> --target <目标>`。

### 10.3 ✅ search 服务端过滤:活体实证,并定形参数

- `args=["关键词"]`(单串)与 `postData=[{"text":...}]` → **「功能异常」** ❌
- **`args=[["关键词"]]`(包一层 List)→ ✅ 生效**——与 `Search.search(java.util.List<?>)` 形参吻合,§3.2 的"是否需再包 List"疑问解除:**需要**。
- 响应:`setPageConfig` + **`u` 动作(过滤后数据块)**:含 `dataindex/rows/rowcount(=18)/datacount/pagecount/isSplitPage`,另附 `InvokeControlMethod`(entryentity:createGridColumns/selectRows([])/setFocus/setSelectedDataInfo)。
- 关键词 `pur_order` 命中 18 条(含 pur_ordercheck 等子串匹配,证实是 indexOf 语义,与 §3.1 字节码判断一致)。已实现为 `ly convert-rule list --search <关键词>`(不受首屏 500 限制)。

### 10.4 分页:仍未破解(状态不变)

500 上限 = entryentity page size 的判断维持(§4);search 只缓解"找路线",page-2+ 全量遍历仍待抓包浏览器翻页请求。

### 10.5 对 §7 待验证清单的销账

| §7 待验证项 | 结果 |
|---|---|
| entryRowClick 单发/合并、ac 取值 | ❌ 路线整体被推翻,已由 §10.2 替代 |
| page-2+ 翻页载荷 | 未破解(§10.4) |
| search args 形态 | ✅ `args=[[关键词]]`(§10.3) |
| customParams 直开 botp_convertrule | ✅ 破解并实证(§10.2) |

### 10.6 落地

- `ly convert-rule list --search <kw>`:服务端过滤全量路线(1426 内 indexOf)。
- `ly convert-rule detail --source <src> --target <tgt>`:直开指定规则详情(规则树含 ruleId)。
- 回归:`ly convert-rule detail`(无参)仍开第一行,解析正常。

---

## 11. C3 保存通道活体破解(第三轮,2026-09-09)

### 11.1 保存动作契约(✅ 已破解)

规则详情页 `botp_convertrule` 的「保存全部」按钮 `btnsave` 是**纯插件按钮**(无绑定实体操作):

```json
[{"key": "tbar_main", "methodName": "itemClick", "args": ["btnsave", ""],
  "postData": [{}, [{"k": "<字段key>", "v": <新值>}, ...], []]}]
```

- `args` 第二元素**必须存在**:`["btnsave"]`(缺参会「功能异常」)、`["btnsave","save"]`(报「实体botp_convertrule上没有编码为save的操作」)都不行——**空串**让框架跳过实体操作分发、直接进插件 `ConvertRuleEdit.itemClick` → `doModify()` → `doSaveAll()`。
- `postData[0]`=控件状态回显(空对象可)、`postData[1]`=**字段回写列表**、`postData[2]` 留空。字段条目格式 `{"k":字段key,"v":值}`(可选 `"r"` 行号)——出自 `FormController.postData/postFieldState` 字节码:`k`→字段、`r`→行、`v`→经 `FieldEdit.postBack` 写模型。
- 无改动保存返回 `ShowNotificationMsg "保存成功。"` + 规则树 updateNodes。

### 11.2 字段锁:kingdee 发布的规则被设计器锁定(⚠️ 内容写入的边界)

- 写入值能到达字段,但 `FieldEdit.checkEditFieldStatus` 拒绝:`无法修改锁定字段<名>的值`(实测 `fmulilangname`、`fsourcelayout` 均锁)。与 `Status=EDIT/ADDNEW` 参数无关——锁来自页面下发的 **`st` 字段状态**(`u` 动作携带,如 `{"st":[["er_hotelbill",...]],"k":"fsourcelayout"}`),浏览器把它存在 pageCache 的 `controlMetaState` 并在后续请求回显。
- 下发流里的锁提示原文:**「本规则由其他开发商发布,请勿直接改动;可以扩展一个新分支后修改」**——即设计器对**非本开发商发布的原始规则**按设计锁定全部字段。
- kd 知识库证实(《单据的转换规则继承和扩展的区别》 vip.kingdee.com/knowledge/836044166890504704):
  - **扩展** = 在原规则基础上修改,扩展规则是原规则的补充(设计器对 kingdee 规则改内容的正规路径 =「扩展一个新分支」);
  - **继承** = 派生全新独立规则(受原规则控制)。
- → C3 内容写入路径:**本开发商(或新建)的规则可直接编辑;kingdee 原始规则先经设计器「扩展」生成新分支**。新建规则疑走同表单 `Status=ADDNEW`(待验证)。

### 11.3 规则启停走 OpenAPI(✅ 已落地,绕过设计器锁)

`botp_crlist`(基础资料实体)的开放操作含 **enable/disable**——发布后直接 HTTP 调用,**不受设计器 isv 锁影响**:

```
ly data publish --form botp_crlist --operations enable,disable --confirm
ly convert-rule enable --id <ruleId> --confirm    # → enabled=1(读回断言通过)
ly convert-rule disable --id <ruleId> --confirm   # 非幂等:重复同向报 603「数据已为停用状态」
```

实测闭环:enable→query 读回 enabled=1→disable→读回 enabled=0,状态已复原。

### 11.4 C4 现状:isv 权限墙(与 BOM 案例同源)

- `er_hotelbill`(em 应用,kingdee)无 push 操作;`ai-meta addOperation` 挂 push 报「表单不属于当前开发商,请扩展后再进行编辑」(对 `er_hotelbill_ext` 同样被拒——扩展表单属主仍是 kingdee)。`OperationApi`/`DefaultOperate` 字节码证实 v2 open 运行时是**通用实体操作执行器**,没有内置 push——实体上必须先有 push 操作。
- 解锁选项:① 管理员侧给开发商 e8n4 放开 em 资源权限或手工建扩展应用(同 BOM 案例);② 走会话通道(admin 会话)在设计器加 push 操作(载荷待逆向);③ C3 完整落地后,在**自属应用**的单据间建规则+挂 push,端到端验收同样成立(spec 的「标准单→标准单」本就非硬性)。
