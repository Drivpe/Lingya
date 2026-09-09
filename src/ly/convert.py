"""ly convert-rule — 单据转换(BOTP)规则只读通道 v2(工单 #13 / C2)。

苍穹无 BOTP OpenAPI(调研 docs/research-转换规则端点契约调研.md §2/§8),
文档 docs/research/2026-09-09-batchInvokeAction-选中态与过滤契约.md,双通道拼图:
  - list  走 Web 会话通道:botp_convertpath(转换路线列表)getConfig→loadData,
          返回环境内全部转换路线(源单/目标单编码+名称)。限制:服务端分页 500 条/页,
          目前仅首屏可取(page 2+ 传输格式未破解);--search 走服务端过滤(searchpath
          .search,对全量缓存 indexOf 匹配)不受首屏限制。
  - get   走 OpenAPI 通道:botp_crlist(转换规则,基础资料实体,物理表 T_BOTP_ConvertRule)
          已发布 query 契约(--query-id-optional),按 ruleId 精确读整行。
  - detail 走 Web 会话通道:--source/--target 直开指定规则详情(getConfig 自定义
          参数 SourceBill/TargetBill,活体实证);无参数时 modify 链打开第一行。
          解析出规则树(ruleId)、表单字段值、字段映射网格——C3 写入复用同一会话。
"""

from __future__ import annotations

import json
import re

from . import api as ly_api
from .session import SessionError, WebSession

PATH_FORM = "botp_convertpath"   # 转换路线列表(DynamicFormModel,仅会话通道)
RULE_FORM = "botp_crlist"        # 转换规则(基础资料,物理表 T_BOTP_ConvertRule,OpenAPI 可查)
RULE_EDIT_FORM = "botp_convertrule"  # 规则详情页表单(会话通道打开/保存)
QUERY_PATH = f"/kapi/v2/open/{RULE_FORM}/query"


def _session(env: dict, web_user: str | None = None,
             web_password: str | None = None) -> WebSession:
    """按环境配置构造并登录 Web 会话;web 凭证取参数 > env 配置。"""
    user = web_user or env.get("_raw", {}).get("webUser") or ""
    password = web_password or env.get("_raw", {}).get("webPassword") or ""
    if not user or not password:
        raise SessionError(
            "缺少 Web 会话凭证(设计器通道需要账号密码,与 OpenAPI 凭证独立);"
            "先 `ly auth web-add --user <账号> --password <密码>` 存入环境配置")
    s = WebSession(env["url"], env["accountId"], user, password)
    s.login()
    return s


# ── list:转换路线列表(会话通道) ─────────────────────────────────────────────
def list_paths(env: dict, source: str | None = None, target: str | None = None,
               keyword: str | None = None, web_user: str | None = None,
               web_password: str | None = None) -> dict:
    """拉取转换路线首屏(≤500 条)并在客户端按源单/目标单/关键词过滤。

    返回 {"total_in_env": int, "fetched": int, "matched": int, "paths": [...]}。
    """
    s = _session(env, web_user, web_password)
    pid = s.open_form(PATH_FORM)
    acts = s.invoke(PATH_FORM, "loadData", pid,
                    [{"key": "", "methodName": "loadData", "args": [], "postData": []}])
    data = next((a["p"][0]["data"] for a in acts
                 if isinstance(a.get("p"), list) and a["p"]
                 and isinstance(a["p"][0], dict) and "data" in a["p"][0]), None)
    if data is None:
        raise SessionError("转换路线列表响应无数据块")
    idx = data["dataindex"]
    kw = (keyword or "").lower()
    paths = []
    for r in data.get("rows") or []:
        src = r[idx["fsourceentitynumber"]] or ""
        tgt = r[idx["ftargetentitynumber"]] or ""
        if source and src != source:
            continue
        if target and tgt != target:
            continue
        if kw and kw not in f"{src}|{r[idx['fsourceentityname']] or ''}|{tgt}|{r[idx['ftargetentityname']] or ''}".lower():
            continue
        paths.append({"seq": r[idx.get("seq", 1)], "source": src,
                      "source_name": r[idx["fsourceentityname"]] or "",
                      "target": tgt, "target_name": r[idx["ftargetentityname"]] or ""})
    return {"total_in_env": data["rowcount"], "fetched": len(data.get("rows") or []),
            "matched": len(paths), "paths": paths}


# ── get:按 ruleId 读规则整行(OpenAPI 通道) ─────────────────────────────────
def get_rule(env: dict, rule_id: str) -> dict:
    body = ly_api.call(env, "GET",
                       f"{QUERY_PATH}?{__import__('urllib.parse', fromlist=['urlencode']).urlencode({'id': str(rule_id), 'pageNo': 1, 'pageSize': 1})}")
    if not body.get("status"):
        from .envelope import fail
        fail("api", body.get("errorCode"), body.get("message", "query 失败"),
             "契约未发布:ly data publish --form botp_crlist --operations query "
             "--query-id-optional --query-filter-fields number,name,sourceentitynumber,targetentitynumber,enabled,defrule --confirm")
    rows = (body.get("data") or {}).get("rows") or []
    if not rows:
        from .envelope import fail
        fail("api", "not_found", f"ruleId={rule_id} 无匹配规则",
             "先 `ly convert-rule list` 找路线;ruleId 可经 detail 子命令或设计器规则树获取")
    return rows[0]


# ── enable/disable:规则启停(OpenAPI 通道,2026-09-09 实测闭环) ────────────────
def set_rule_enabled(env: dict, rule_id: str, enable: bool) -> dict:
    """启用/停用转换规则,并 query 读回断言。前提:ly data publish
    --form botp_crlist --operations enable,disable --confirm(先发布一次)。

    实测语义:对已停用规则再 disable 报 603「数据已为停用状态」(状态前置校验,
    非幂等);写入走 T_BOTP_ConvertRule 物理表,不受设计器「其他开发商发布」
    锁定影响(锁定只作用于设计器 UI 的字段回写)。
    返回含 `enabled`(操作后 query 读回值,0/1)供调用方断言。
    """
    op = "enable" if enable else "disable"
    body = ly_api.call(env, "POST", f"/kapi/v2/open/{RULE_FORM}/{op}",
                       payload={"data": {"id": str(rule_id)}})
    if not body.get("status"):
        from .envelope import fail
        fail("api", body.get("errorCode"),
             body.get("message", f"{op} 失败"),
             "先发布:ly data publish --form botp_crlist --operations enable,disable --confirm;"
             "状态前置不满足(如重复同向操作)会报错")
    d = body.get("data") or {}
    result = d.get("result") or []
    errs = [e for r in result for e in (r.get("errors") or [])]
    row = get_rule(env, rule_id)
    return {"operation": op, "id": str(rule_id),
            "successCount": d.get("successCount"), "totalCount": d.get("totalCount"),
            "failCount": d.get("failCount"), "errors": errs,
            "enabled": row.get("enabled")}


# ── detail:规则详情解析(会话通道) ──────────────────────────────────────────
_LOAD_DATA = [{"key": "", "methodName": "loadData", "args": [], "postData": []}]
_MODIFY_POST = [{"treeviewap": {"focus": {"id": "0", "parentid": "", "text": "业务云",
                                          "isParent": True}}}, []]

# btnsave 写通道契约(2026-09-09 活体破解,§11.1 + ClassCast 修正):
# postData 三段 [控件状态Map, 字段回写List, 子表单状态Map] —— 第三段必须是
# Map({}),给 [] 会 ArrayList→Map ClassCastException(框架 FormController.postData)。
_BTN_SAVE = "btnsave"


def _field_entries(fields: dict) -> list:
    """{"k":v} → [{"k":k,"v":v}];fname 与 fmulilangname 成对写(多语言代理)。"""
    entries = []
    for k, v in fields.items():
        entries.append({"k": k, "v": v})
    if "fname" in fields and "fmulilangname" not in fields:
        entries.append({"k": "fmulilangname", "v": {"zh_CN": fields["fname"]}})
    return entries


def _open_rule_page(s, source: str, target: str, status: str | None = None) -> str:
    extra = {"SourceBill": source, "TargetBill": target}
    if status:
        extra["Status"] = status
    return s.open_form(RULE_EDIT_FORM, extra_params=extra)


def _load_and_parse(s, page_id: str) -> dict:
    t3 = s.raw_invoke(RULE_EDIT_FORM, "loadData", page_id, _LOAD_DATA)
    return parse_detail(t3)


def _btnsave(s, page_id: str, entries: list) -> dict:
    """btnsave 写入并解析响应。成功标志=updateNodes 动作且无错误对话框。"""
    params = [{"key": "tbar_main", "methodName": "itemClick",
               "args": [_BTN_SAVE, ""], "postData": [{}, entries, {}]}]
    acts = s.invoke(RULE_EDIT_FORM, "itemClick", page_id, params)
    msgs: list = []
    dialog = None
    updated = False
    for a in acts:
        if not isinstance(a, dict):
            continue
        p = a.get("p")
        if isinstance(p, list):
            for c in p:
                if isinstance(c, dict) and c.get("methodname") == "updateNodes":
                    updated = True
                if isinstance(c, dict) and c.get("methodname") == "ShowNotificationMsg":
                    msgs.extend(str(x) for x in (c.get("args") or []))
        if isinstance(p, dict) and p.get("caption"):
            dialog = p["caption"]
    return {"saved": bool(updated and not dialog), "messages": msgs, "dialog": dialog}


def _rows_from_data(data: dict) -> list:
    """数据块 → 路线路字典列表(seq/源/目标编码+名称)。"""
    idx = data["dataindex"]
    out = []
    for r in data.get("rows") or []:
        out.append({"seq": r[idx.get("seq", 1)],
                    "source": r[idx["fsourceentitynumber"]] or "",
                    "source_name": r[idx["fsourceentityname"]] or "",
                    "target": r[idx["ftargetentitynumber"]] or "",
                    "target_name": r[idx["ftargetentityname"]] or ""})
    return out


def search_paths(env: dict, keyword: str, web_user: str | None = None,
                 web_password: str | None = None) -> dict:
    """服务端过滤搜索转换路线(searchpath.search,活体实证 2026-09-09)。

    与 list_paths 的客户端过滤不同:search 在服务端对全量 1426 条缓存做
    源/目标编码+名称的 indexOf 子串匹配,不受首屏 500 条限制。
    注意:args 必须是包一层 List 的形态 [["关键词"]],单串会报「功能异常」。
    返回 {"total_in_env", "matched", "paths"}。
    """
    s = _session(env, web_user, web_password)
    pid = s.open_form(PATH_FORM)
    s.invoke(PATH_FORM, "loadData", pid, _LOAD_DATA)
    acts = s.invoke(PATH_FORM, "search", pid,
                    [{"key": "searchpath", "methodName": "search",
                      "args": [[keyword]], "postData": []}])
    data = None
    for a in acts:
        if isinstance(a, dict) and a.get("a") == "u" and isinstance(a.get("p"), list):
            for it in a["p"]:
                if isinstance(it, dict) and isinstance(it.get("data"), dict) \
                        and "rows" in it["data"]:
                    data = it["data"]
    if data is None:
        raise SessionError("search 响应无数据块")
    return {"total_in_env": data.get("datacount", len(data.get("rows") or [])),
            "matched": len(data.get("rows") or []),
            "paths": _rows_from_data(data)}


def rule_detail(env: dict, source: str, target: str,
                web_user: str | None = None,
                web_password: str | None = None) -> dict:
    """直开指定源/目标对的规则详情(getConfig 自定义参数路线,活体实证)。

    服务端 FormShowParameter.createFormShowParameter 会把 params JSON 里
    非 bean 属性的剩余键 setCustomParam(k,v);ConvertRuleEdit 从
    getCustomParam("SourceBill"/"TargetBill") 取源/目标加载规则——
    无需网格选中(网格选中态在无头通道不可传,entryRowClick 不写模型当前行)。
    """
    s = _session(env, web_user, web_password)
    pid = _open_rule_page(s, source, target, None)
    out = _load_and_parse(s, pid)
    out["source"] = source
    out["target"] = target
    return out


def first_path_detail(env: dict, web_user: str | None = None,
                      web_password: str | None = None) -> dict:
    """modify 链打开第一行路线的规则详情,解析规则树/表单值/字段映射网格。"""
    s = _session(env, web_user, web_password)
    pid = s.open_form(PATH_FORM)
    s.invoke(PATH_FORM, "loadData", pid, _LOAD_DATA)
    t2 = s.raw_invoke(PATH_FORM, "modify", pid,
                      [{"key": "tbar_main", "methodName": "itemClick",
                        "args": ["btnmodify", "modify"],
                        "postData": _MODIFY_POST}])
    j2 = json.loads(t2)
    show = next((a for a in j2 if isinstance(a, dict) and a.get("a") == "showForm"), None)
    if not show:
        raise SessionError(f"modify 未返回 showForm: {t2[:200]}")
    pid2 = show["p"][0]["pageId"]
    t3 = s.raw_invoke(RULE_EDIT_FORM, "loadData", pid2,
                      _LOAD_DATA)
    return parse_detail(t3)


def parse_detail(raw: str) -> dict:
    """解析规则详情动作流:规则树节点、表单字段值、各策略网格行。"""
    j = json.loads(raw)
    out: dict = {"form_values": {}, "rules": [], "grids": {}}
    for a in j:
        if not isinstance(a, dict):
            continue
        if a.get("a") == "u":
            for item in a.get("p") or []:
                if isinstance(item, dict) and "k" in item:
                    out["form_values"][item["k"]] = item.get("v")
        p = a.get("p")
        if not isinstance(p, list):
            continue
        for c in p:
            if not isinstance(c, dict):
                continue
            if c.get("key") == "tv_rules" and c.get("methodname") in ("addNodes", "addNode"):
                for arg in c.get("args") or []:
                    for node in (arg if isinstance(arg, list) else [arg]):
                        if isinstance(node, dict) and "id" in node:
                            out["rules"].append({"rule_id": node["id"], "text": node.get("text", "")})
            elif c.get("methodname") in ("setRows", "addRows", "insertRows") and c.get("key"):
                rows = (c.get("args") or [[]])[0] if c.get("args") else []
                out["grids"].setdefault(c["key"], []).extend(
                    rows if isinstance(rows, list) else [rows])
    return out


# ── new/save:规则写入(会话通道,C3/#15,2026-09-09 活体闭环) ───────────────────
def new_rule(env: dict, source: str, target: str, name: str,
             fields: dict | None = None,
             web_user: str | None = None,
             web_password: str | None = None) -> dict:
    """新建(或打开路线既有骨架行)转换规则并保存名称/字段值。

    实测语义(2026-09-09):Status=ADDNEW + SourceBill/TargetBill 直开;
    **loadData 时服务端即落库骨架行**(fid 预分配,fdata=默认 XML)——
    路线已有规则时复用该行(同 id),不会建第二条。名称写 fname+
    fmulilangname(多语言代理,成对写)。返回含 rule_id 与 OpenAPI 读回值。
    """
    from .envelope import fail
    s = _session(env, web_user, web_password)
    pid = _open_rule_page(s, source, target, "ADDNEW")
    d = _load_and_parse(s, pid)
    rid = (d["rules"] or [{}])[0].get("rule_id")
    if not rid:
        fail("session", "no_rule_allocated", "ADDNEW 页未预分配 rule_id",
             "确认源/目标单编码存在;详情见 docs/research/2026-09-09-batchInvokeAction §10.2")
    f = dict(fields or {})
    f.setdefault("fname", name)
    res = _btnsave(s, pid, _field_entries(f))
    if not res["saved"]:
        fail("session", "save_rejected",
             f"btnsave 被拒: {res['dialog'] or res['messages']}",
             "kingdee 发布的规则字段被 st 锁定(§11.2);自有规则可编辑;"
             "载荷第三段必须是 {} 不是 [](FormController.postData ClassCast)")
    row = get_rule(env, rid)
    return {"rule_id": str(rid), "source": source, "target": target,
            "name": name, "readback": {"name": row.get("name"),
                                       "enabled": row.get("enabled"),
                                       "bizappid": row.get("bizappid_number")},
            "saved": True}


def save_rule(env: dict, rule_id: str, fields: dict,
              web_user: str | None = None,
              web_password: str | None = None) -> dict:
    """按 ruleId 编辑既有规则:开路线页→校验当前行匹配→回写字段→btnsave→读回。

    限制:规则定位经 SourceBill/TargetBill(该路线首条规则)——同路线多条
    规则时当前行可能不是目标行,不匹配即报 route_ambiguity(不盲写)。
    kingdee 发布的原始规则字段被 st 锁死(§11.2),只有自有规则可写。
    """
    from .envelope import fail
    row = get_rule(env, rule_id)
    src = row.get("sourceentitynumber_number") or row.get("sourceentitynumber_id")
    tgt = row.get("targetentitynumber_number") or row.get("targetentitynumber_id")
    if not src or not tgt:
        fail("api", "missing_route", f"ruleId={rule_id} 行缺少源/目标实体编码",
             "ly convert-rule get --id 检查 sourceentitynumber_number/targetentitynumber_number")
    s = _session(env, web_user, web_password)
    pid = _open_rule_page(s, src, tgt, None)
    d = _load_and_parse(s, pid)
    opened = (d["rules"] or [{}])[0].get("rule_id")
    if not opened or str(opened) != str(rule_id):
        fail("session", "route_ambiguity",
             f"路线 {src}→{tgt} 当前打开的规则是 {opened},不是目标 {rule_id}",
             "同路线多条规则的场景尚未支持(网格选中态不可 headless 传输,§10.1);"
             "暂用设计器或先停用其他规则")
    res = _btnsave(s, pid, _field_entries(fields))
    if not res["saved"]:
        fail("session", "save_rejected",
             f"btnsave 被拒: {res['dialog'] or res['messages']}",
             "kingdee 规则字段被 st 锁死须先「扩展」分支(§11.2);自有规则可直接编辑")
    row2 = get_rule(env, rule_id)
    return {"rule_id": str(rule_id),
            "readback": {"name": row2.get("name"), "enabled": row2.get("enabled"),
                         "modifydate": row2.get("modifydate")},
            "saved": True, "messages": res["messages"]}
