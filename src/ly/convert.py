"""ly convert-rule — 单据转换(BOTP)规则只读通道 v2(工单 #13 / C2)。

苍穹无 BOTP OpenAPI(调研 docs/research-转换规则端点契约调研.md §2/§8),双通道拼图:
  - list  走 Web 会话通道:botp_convertpath(转换路线列表)getConfig→loadData,
          返回环境内全部转换路线(源单/目标单编码+名称)。限制:服务端分页 500 条/页,
          目前仅首屏可取(page 2+ 传输格式未破解),全量见 issue #13 备注。
  - get   走 OpenAPI 通道:botp_crlist(转换规则,基础资料实体,物理表 T_BOTP_ConvertRule)
          已发布 query 契约(--query-id-optional),按 ruleId 精确读整行。
  - detail 走 Web 会话通道:modify 链打开规则详情(当前固定落在本页第一行,
          网格选中态的传输格式未破解,见 #13),解析出规则树(ruleId)、表单字段值、
          字段映射网格——证明详情解析链路,C3 写入复用同一会话。
"""

from __future__ import annotations

import json
import re

from . import api as ly_api
from .session import SessionError, WebSession

PATH_FORM = "botp_convertpath"   # 转换路线列表(DynamicFormModel,仅会话通道)
RULE_FORM = "botp_crlist"        # 转换规则(基础资料,物理表 T_BOTP_ConvertRule,OpenAPI 可查)
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


# ── detail:规则详情解析(会话通道,当前固定打开本页第一行) ──────────────────
def first_path_detail(env: dict, web_user: str | None = None,
                      web_password: str | None = None) -> dict:
    """modify 链打开第一行路线的规则详情,解析规则树/表单值/字段映射网格。"""
    s = _session(env, web_user, web_password)
    pid = s.open_form(PATH_FORM)
    s.invoke(PATH_FORM, "loadData", pid,
             [{"key": "", "methodName": "loadData", "args": [], "postData": []}])
    t2 = s.raw_invoke(PATH_FORM, "modify", pid,
                      [{"key": "tbar_main", "methodName": "itemClick",
                        "args": ["btnmodify", "modify"],
                        "postData": [{"treeviewap": {"focus": {"id": "0", "parentid": "",
                                                               "text": "业务云", "isParent": True}}}, []]}])
    j2 = json.loads(t2)
    show = next((a for a in j2 if isinstance(a, dict) and a.get("a") == "showForm"), None)
    if not show:
        raise SessionError(f"modify 未返回 showForm: {t2[:200]}")
    pid2 = show["p"][0]["pageId"]
    t3 = s.raw_invoke(RULE_FORM.replace("crlist", "convertrule"), "loadData", pid2,
                      [{"key": "", "methodName": "loadData", "args": [], "postData": []}])
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
