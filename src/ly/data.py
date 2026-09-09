"""ly data — 业务数据通道(开放平台 v2 零代码操作 API)。

前置链路(本模块):
  precheck  对指定表单做「可被业务 API 操作」四项检查(表单存在/元数据可取/操作可查/开放平台在线)
  publish   按 getEntityType 元数据自动构造并注册 v2 操作 API(genV2ApiByMetaData, upsert by urlformat)

契约来源:灵基 app-build openapi-gen 技能(2026-09-07 实测移植);响应均为苍穹统一契约
{status, errorCode, message, data}。genV2ApiByMetaData 是「整体替换」语义——
body['data'] 必须显式携带 bodyentryentity/respentryentity/filter_entity 三大子表,
缺失会被空数组覆盖(可能清空已有 query API 的返回参数),故所有提交走 submit_api_payload() 的不变量校验。
"""

from __future__ import annotations

import json
import random
import time
import urllib.parse

from . import api as ly_api
from .envelope import fail

# ── 端点(管理类接口走 /kapi/ 前缀) ────────────────────────────────────────────
GEN_V2_API_PATH = "/kapi/v2/open/openapi_apilist/genV2ApiByMetaData"
GET_ENTITY_OPERATIONS_PATH = "/kapi/v2/open/openapi/getEntityOperations"

OPERATION_CN = {
    "save": "保存", "query": "查询", "delete": "删除", "submit": "提交",
    "unsubmit": "撤销", "audit": "审核", "unaudit": "反审核",
    "enable": "启用", "disable": "禁用",
}

# ── 元数据 _Type_ → 参数类型/字段类型映射(来源 openapi-gen constants/parser) ──
BASEDATA_PROP_TYPES = {
    "BasedataProp", "OrgProp", "MainOrgProp", "UserProp", "CreaterProp",
    "ModifierProp", "CurrencyProp", "MaterielProp", "UnitProp",
    "BillTypeProp", "ItemClassProp", "RefBillProp", "BasedataPropProp",
    "AssistantProp",
}
PROP_TO_PARAMTYPE = {
    "TextProp": "String", "VarcharProp": "String", "MuliLangTextProp": "String",
    "LargeTextProp": "String", "TextAreaProp": "String", "BillNoProp": "String",
    "ComboProp": "String", "MulComboProp": "String", "BillStatusProp": "String",
    "ItemClassTypeProp": "String",
    "LongProp": "Long", "BigIntProp": "Long",
    "IntegerProp": "Integer", "TimeProp": "Integer",
    "DecimalProp": "Decimal", "PriceProp": "Decimal",
    "QtyProp": "Decimal", "AmountProp": "Decimal",
    "BooleanProp": "Boolean",
    "DateProp": "Date",
    "DateTimeProp": "DateTime", "CreateDateProp": "DateTime", "ModifyDateProp": "DateTime",
    "FlexProp": "Flex",
    "PictureProp": "String", "UserAvatarProp": "String", "TimeRangeProp": "String",
}
PROP_TYPE_TO_FIELD_TYPE = {
    "TextProp": "TextField", "MuliLangTextProp": "MuliLangTextField",
    "IntegerProp": "IntegerField", "BigIntProp": "BigIntField",
    "DecimalProp": "DecimalField", "PriceProp": "PriceField",
    "QtyProp": "QtyField", "AmountProp": "AmountField",
    "DateProp": "DateField", "DateTimeProp": "DateTimeField",
    "CreateDateProp": "CreateDateField", "ModifyDateProp": "ModifyDateField",
    "TimeProp": "TimeField", "BooleanProp": "CheckBoxField",
    "BillStatusProp": "BillStatusField", "ComboProp": "ComboField",
    "MulComboProp": "MulComboField", "BasedataProp": "BasedataField",
    "OrgProp": "OrgField", "MainOrgProp": "OrgField", "UserProp": "UserField",
    "CreaterProp": "CreaterField", "ModifierProp": "ModifierField",
    "CurrencyProp": "CurrencyField", "MaterielProp": "MaterielField",
    "UnitProp": "UnitField", "BillTypeProp": "BillTypeField",
    "FlexProp": "FlexField", "MulBasedataProp": "MulBasedataField",
    "AssistantProp": "AssistantField", "ItemClassTypeProp": "ItemClassTypeField",
    "ItemClassProp": "ItemClassField", "RefBillProp": "RefBillField",
    "BasedataPropProp": "BasedataPropField", "PictureProp": "PictureField",
    "UserAvatarProp": "UserAvatarField", "TextAreaProp": "TextAreaField",
    "BillNoProp": "BillNoField", "TimeRangeProp": "TimeRangeField",
}
SKIP_PROP_TYPES = {"LongProp", "LinkEntryProp", "ModifierIdProp", "DynamicLocaleProperty"}

MAX_PARAMNAME_LEN = 50
BODY_ROW_REQUIRED = ("paramname", "paramtype", "must", "body_level", "bodyparamdes", "example")
RESP_ROW_REQUIRED = ("respparamname", "respparamtype", "resp_level", "respdes", "respexample")
FILTER_ROW_REQUIRED = ("filter_column", "filter_compare")


class PayloadInvariantError(ValueError):
    """提交前不变量校验失败——禁止把不完整 body 发到后端(整体替换语义会破坏已有 API)。"""


# ── 小工具 ────────────────────────────────────────────────────────────────────
def _display(v) -> str:
    """DisplayName 可能是 {zh_CN, GLang} 或纯串。"""
    if isinstance(v, dict):
        return v.get("zh_CN") or v.get("GLang") or ""
    return v or ""


def _prop_type_to_paramtype(prop_type: str) -> str | None:
    if prop_type in BASEDATA_PROP_TYPES:
        return None
    return PROP_TO_PARAMTYPE.get(prop_type, "String")


def _body_data_model(prop_type: str) -> str:
    return "TextProp" if prop_type == "ItemClassTypeProp" else prop_type


def _snowflake() -> str:
    return f"{int(time.time() * 1000) % 10**9:09d}{random.randrange(10**9):09d}"


def _example(paramtype: str) -> str:
    t = (paramtype or "").strip()
    if t == "Entries":
        return "[{},{}]"
    if t == "Long":
        return '"' + str(random.randint(1, 9)) + "".join(str(random.randint(0, 9)) for _ in range(17)) + '"'
    if t == "String":
        return '"' + "".join(random.choices("abcdefghijkmnpqrstuvwxyz", k=5)) + '"'
    if t == "Integer":
        return "1"
    if t == "Boolean":
        return "false"
    if t == "Decimal":
        return "0.00"
    if t == "Date":
        return '"2024-01-01"'
    if t == "DateTime":
        return '"2024-01-01 00:00:00"'
    if t == "Flex":
        return "{}"
    return '"abcde"'


def _truncate(name: str) -> str:
    if len(name) <= MAX_PARAMNAME_LEN:
        return name
    parts = name.split("_")
    if len(parts) <= 2:
        return name[:MAX_PARAMNAME_LEN]
    first, mid, last = parts[0][:8], "_".join(p[:4] for p in parts[1:-2]), "_".join(parts[-2:])
    return f"{first}_{mid}_{last}"[:MAX_PARAMNAME_LEN]


# ── getEntityType JSON → BillEntity ──────────────────────────────────────────
def parse_entity_type_json(data) -> dict:
    obj = json.loads(data) if isinstance(data, str) else data
    bill = {
        "entityname": obj.get("Name", ""),
        "displayname": _display(obj.get("DisplayName")),
        "bizappid": obj.get("AppId", ""),
        "bizAppNumber": obj.get("BizAppNumber", ""),
        "fields": [],
        "entries": [],
    }
    for prop in obj.get("Properties", []):
        ptype, pname = prop.get("_Type_", ""), prop.get("Name", "")
        pdisplay = _display(prop.get("DisplayName"))
        if ptype == "EntryProp":
            bill["entries"].append(_parse_entry(pname, pdisplay, prop))
            continue
        if ptype in SKIP_PROP_TYPES or not pname:
            continue
        bill["fields"].append({
            "name": pname, "displayname": pdisplay, "propType": ptype,
        })
    return {"BillEntity": bill}


def _parse_entry(name, display, prop) -> dict:
    info = {"name": name, "displayname": display, "fields": [], "subentries": []}
    item = prop.get("ItemType") or {}
    for ep in item.get("Properties", []):
        etype, ename = ep.get("_Type_", ""), ep.get("Name", "")
        edisplay = _display(ep.get("DisplayName"))
        if etype == "SubEntryProp":
            info["subentries"].append(_parse_entry(ename, edisplay, ep))
            continue
        if etype in SKIP_PROP_TYPES or not ename:
            continue
        info["fields"].append({"name": ename, "displayname": edisplay, "propType": etype})
    return info


# ── save bodyentryentity 构造(规则 A~E) ──────────────────────────────────────
def build_save_body_entries(metadata: dict) -> list[dict]:
    bill = metadata.get("BillEntity", {})
    result: list[dict] = []
    # 规则 A: 主表 id 显式添加(LongProp 被 SKIP 跳过)
    result.append({"paramname": "id", "objpropname": "id", "paramtype": "Long",
                   "must": "0", "body_level": "1", "bodyparamdes": "id",
                   "example": _example("Long"), "body_data_model": "LongProp",
                   "is_unique_key": True})
    for f in bill.get("fields", []):
        name = f.get("name", "")
        if not name or name == "id":
            continue
        _append_field(result, name, f.get("propType", ""),
                      f.get("displayname", name), "1", None)
    for entry in bill.get("entries", []):
        ename, edisplay = entry.get("name", ""), entry.get("displayname", entry.get("name", ""))
        pid = _snowflake()
        result.append({"paramname": ename, "objpropname": ename, "paramtype": "Entries",
                       "must": "0", "body_level": "1", "bodyparamdes": edisplay,
                       "example": "[{},{}]", "body_data_model": "EntryProp",
                       "is_unique_key": False, "id": pid})
        result.append({"paramname": _truncate(f"{ename}_id"), "objpropname": f"{ename}.id",
                       "paramtype": "Long", "must": "0", "body_level": "2",
                       "bodyparamdes": f"{edisplay}-id", "example": _example("Long"),
                       "body_data_model": "LongProp", "is_unique_key": True, "pid": pid})
        for ef in entry.get("fields", []):
            efname = ef.get("name", "")
            if not efname or efname == "id":
                continue
            _append_field(result, f"{ename}_{efname}", ef.get("propType", ""),
                          ef.get("displayname", efname), "2", pid,
                          objpropname_prefix=f"{ename}.")
        for sub in entry.get("subentries", []):
            sname, sdisplay = sub.get("name", ""), sub.get("displayname", sub.get("name", ""))
            spid = _snowflake()
            result.append({"paramname": _truncate(f"{ename}_{sname}"),
                           "objpropname": f"{ename}.{sname}", "paramtype": "Entries",
                           "must": "0", "body_level": "2", "bodyparamdes": sdisplay,
                           "example": "[{},{}]", "body_data_model": "EntryProp",
                           "is_unique_key": False, "id": spid, "pid": pid})
            result.append({"paramname": _truncate(f"{ename}_{sname}_id"),
                           "objpropname": f"{ename}.{sname}.id", "paramtype": "Long",
                           "must": "0", "body_level": "3", "bodyparamdes": f"{sdisplay}-id",
                           "example": _example("Long"), "body_data_model": "LongProp",
                           "is_unique_key": True, "pid": spid})
            for sf in sub.get("fields", []):
                sfname = sf.get("name", "")
                if not sfname or sfname == "id":
                    continue
                _append_field(result, f"{ename}_{sname}_{sfname}", sf.get("propType", ""),
                              sf.get("displayname", sfname), "3", spid,
                              objpropname_prefix=f"{ename}.{sname}.")
    return result


def _append_field(result, param_prefix, prop_type, display, level, pid,
                  objpropname_prefix=""):
    # 显示名可能为空(系统字段常见),bodyparamdes/respdes 是服务端必填,回退到参数名
    display = display or param_prefix
    raw = param_prefix.rsplit("_", 1)[-1]
    obj_base = f"{objpropname_prefix}{raw}" if objpropname_prefix else param_prefix
    common = {"must": "0", "body_level": level, "is_unique_key": False}
    if pid is not None:
        common["pid"] = pid
    if prop_type in BASEDATA_PROP_TYPES:
        result.append({**common, "paramname": _truncate(f"{param_prefix}_number"),
                       "objpropname": f"{obj_base}.number", "paramtype": "String",
                       "bodyparamdes": f"{display}-编码", "example": _example("String"),
                       "body_data_model": prop_type})
        result.append({**common, "paramname": _truncate(f"{param_prefix}_id"),
                       "objpropname": f"{obj_base}.id", "paramtype": "Long",
                       "bodyparamdes": f"{display}-ID", "example": _example("Long"),
                       "body_data_model": prop_type})
    elif prop_type == "MulBasedataProp":
        mul_pid = _snowflake()
        result.append({**common, "paramname": _truncate(param_prefix), "objpropname": obj_base,
                       "paramtype": "Entries", "bodyparamdes": display, "example": "[{},{}]",
                       "body_data_model": "MulBasedataProp", "id": mul_pid})
        result.append({"paramname": _truncate(f"{param_prefix}_number"),
                       "objpropname": f"{obj_base}.number", "paramtype": "String",
                       "must": "1", "body_level": str(int(level) + 1),
                       "bodyparamdes": f"{display}-编码", "example": _example("String"),
                       "body_data_model": "MulBasedataProp", "is_unique_key": False,
                       "pid": mul_pid})
    elif prop_type == "FlexProp":
        result.append({**common, "paramname": _truncate(param_prefix), "objpropname": obj_base,
                       "paramtype": "Flex", "bodyparamdes": display, "example": "{}",
                       "body_data_model": "FlexProp"})
    else:
        paramtype = _prop_type_to_paramtype(prop_type)
        if not paramtype:
            return
        result.append({**common, "paramname": _truncate(param_prefix), "objpropname": obj_base,
                       "paramtype": paramtype, "bodyparamdes": display,
                       "example": _example(paramtype),
                       "body_data_model": _body_data_model(prop_type)})


def resp_from_body(body_entries: list[dict]) -> list[dict]:
    id_remap = {e["id"]: _snowflake() for e in body_entries if "id" in e}
    resp = []
    for e in body_entries:
        row = {"respparamname": e["paramname"], "respparamtype": e["paramtype"],
               "respparammust": e.get("must", "0"), "resp_level": e["body_level"],
               "respdes": e.get("bodyparamdes", ""), "respexample": e.get("example", ""),
               "respobjpropname": e.get("objpropname", ""),
               "resp_data_model": e.get("body_data_model", "")}
        if "id" in e:
            row["id"] = id_remap[e["id"]]
        if "pid" in e:
            row["pid"] = id_remap.get(e["pid"], e["pid"])
        resp.append(row)
    return resp


ID_FILTER = [{"filter_column": "id", "filter_compare": "EQUAL",
              "filter_value": "id", "filter_type": "Long", "filter_label": "id"}]


def _id_row(must: str = "1") -> dict:
    return {"paramname": "id", "objpropname": "id", "paramtype": "Long", "must": must,
            "body_level": "1", "bodyparamdes": "id", "example": _example("Long"),
            "body_data_model": "LongProp", "is_unique_key": True}


# ── 不变量校验与提交 ─────────────────────────────────────────────────────────
def _validate_invariants(operation: str, data: dict) -> None:
    for key in ("bodyentryentity", "respentryentity", "filter_entity"):
        if key not in data:
            raise PayloadInvariantError(
                f"genV2ApiByMetaData 是替换语义, data 必须显式包含 {key}")
    if operation == "query" and not data.get("respentryentity"):
        raise PayloadInvariantError("operation=query 时 respentryentity 不能为空")
    for rows, required, section in (
            (data.get("bodyentryentity"), BODY_ROW_REQUIRED, "bodyentryentity"),
            (data.get("respentryentity"), RESP_ROW_REQUIRED, "respentryentity"),
            (data.get("filter_entity"), FILTER_ROW_REQUIRED, "filter_entity")):
        for i, row in enumerate(rows or []):
            for k in required:
                v = row.get(k)
                if v is None or (isinstance(v, str) and not v.strip()):
                    raise PayloadInvariantError(
                        f"operation={operation} 的 {section} 第 {i + 1} 行缺少必填字段 '{k}'")
    seen: dict[str, int] = {}
    for i, row in enumerate(data.get("bodyentryentity") or []):
        name = (row.get("paramname") or "").strip()
        if len(name) > MAX_PARAMNAME_LEN:
            raise PayloadInvariantError(
                f"bodyentryentity 第 {i + 1} 行 paramname 超长(>{MAX_PARAMNAME_LEN}): {name}")
        if name in seen:
            raise PayloadInvariantError(
                f"bodyentryentity paramname 重复: '{name}'(第 {seen[name] + 1}/{i + 1} 行)")
        seen[name] = i


def _submit(env: dict, operation: str, body: dict, took: list) -> tuple[str | None, str | None]:
    """提交一个 API;返回 (api_id, error)。"""
    _validate_invariants(operation, body.get("data") or {})
    t0 = time.time()
    resp = ly_api.call(env, "POST", GEN_V2_API_PATH, payload=body)
    took.append(int((time.time() - t0) * 1000))
    if not resp.get("status"):
        return None, resp.get("message", "未知错误")
    result_list = (resp.get("data") or {}).get("result", [])
    if result_list and result_list[0].get("billStatus"):
        return str(result_list[0].get("id", "")), None
    errors = result_list[0].get("errors", []) if result_list else []
    return None, json.dumps(errors, ensure_ascii=False)


# ── 公共动作 ─────────────────────────────────────────────────────────────────
def call_entity_operations(env: dict, form_number: str) -> list:
    body = ly_api.call(env, "POST", GET_ENTITY_OPERATIONS_PATH,
                       payload={"formNumber": form_number})
    if not body.get("status"):
        raise RuntimeError(body.get("message", "getEntityOperations 失败"))
    return body.get("data") or []


def fetch_metadata(env: dict, entity_number: str) -> dict:
    qs = urllib.parse.urlencode({"entityId": entity_number})
    body = ly_api.call(env, "GET", f"/kapi/v2/devportal/ai-meta/getEntityType?{qs}")
    if not body.get("status"):
        raise RuntimeError(f"getEntityType 失败: {body.get('message', '')[:200]}")
    data = body.get("data")
    if not data:
        raise RuntimeError("getEntityType 返回空 data")
    return parse_entity_type_json(data)


def gen_api(env: dict, bizobject: str, appid: str, name_prefix: str,
            operation: str, metadata: dict, status: str = "C",
            took: list | None = None, query_id_optional: bool = False,
            query_filter_fields: tuple[str, ...] = ()
            ) -> tuple[str | None, str | None, dict | None]:
    """构造并提交单个操作 API;返回 (api_id, error, urlformat)。"""
    op_cn = OPERATION_CN.get(operation, operation)
    urlformat = f"/v2/open/{bizobject}/{operation}"
    body = {"data": {
        "number": f"{bizobject}_{operation}",
        "name": f"{name_prefix}-{op_cn}",
        "httpmethod": "0" if operation == "query" else "1",
        "urlformat": urlformat,
        "apiservicetype": "0",
        "operation": operation,
        "bizobject_number": bizobject,
        "appid_number": appid,
        "version": "2",
        "enable": "1",
        "status": status,
    }}
    save_entries = build_save_body_entries(metadata)
    if operation in ("save", "batchsave"):
        body["data"]["bodyentryentity"] = save_entries
        body["data"]["respentryentity"] = []
        body["data"]["filter_entity"] = []
    elif operation == "query":
        # id 必填=按 id 查单条(默认);id 可选=同契约可分页列全量(C 线 convert-rule list 依赖)
        request_rows = [_id_row(must="0" if query_id_optional else "1")]
        if query_filter_fields:
            # 追加可选业务过滤参数(从元数据头部字段裁剪;BasedataProp 自动拆 _number/_id)
            keep = set(query_filter_fields)
            bill = metadata.get("BillEntity", {})
            trimmed = {"BillEntity": {
                "fields": [f for f in bill.get("fields", []) if f.get("name") in keep],
                "entries": [],
            }}
            missing = keep - {f.get("name") for f in trimmed["BillEntity"]["fields"]}
            if missing:
                raise PayloadInvariantError(f"query-filter-fields 元数据缺字段: {sorted(missing)}")
            request_rows.extend(row for row in build_save_body_entries(trimmed)
                                if row.get("paramname") != "id")
            for row in request_rows:
                if row.get("paramname") != "id":
                    row["must"] = "0"
        body["data"]["bodyentryentity"] = request_rows
        body["data"]["respentryentity"] = resp_from_body(save_entries)
        body["data"]["filter_entity"] = json.loads(json.dumps(ID_FILTER))
    else:
        body["data"]["bodyentryentity"] = [_id_row()]
        body["data"]["respentryentity"] = []
        body["data"]["filter_entity"] = json.loads(json.dumps(ID_FILTER))
    try:
        api_id, err = _submit(env, operation, body, took or [])
    except PayloadInvariantError as e:
        return None, str(e), urlformat
    return api_id, err, urlformat
