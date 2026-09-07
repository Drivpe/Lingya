"""ly convert-rule — 单据转换(BOTP)规则只读通道(工单 #13 / C2)。

苍穹无 BOTP OpenAPI(调研 docs/research-转换规则端点契约调研.md §2 实证),
规则列表/详情经 B 线业务数据通道曲线实现:
  - 转换规则本身是动态表单实体 botp_convertrule(formId 0afd6ae6000003ac);
  - 用 genV2ApiByMetaData 给它发布一条「瘦列表」query 契约(仅头部标量列,
    不含 fieldmappolicy 等 11 个单据体——全量契约实测使开放平台 query 构建器 NPE);
  - list/get 即对该契约做分页查询,id 与业务过滤参数全部可选。
设计器列表插件(ConvertRuleListPlugin)的同款最小集:id + 源单/目标单编码,
外加启用/默认/运行时可见等标量,足够支撑 C4「按环境预置规则现选」。
"""

from __future__ import annotations

import json
import time
import urllib.parse

from . import api as ly_api
from . import data

RULE_FORM = "botp_convertrule"
QUERY_PATH = f"/kapi/v2/open/{RULE_FORM}/query"

# 瘦列表契约的头部字段(实测 getEntityType 属性名;BasedataProp 自动拆 _number/_id 两行)
LIST_HEADER_FIELDS = (
    "fid", "fname", "fsourcebill", "ftargetbill",
    "fsourceentrykey", "ftargetentrykey",
    "fenabled", "fdefault", "fvisibled", "fruncondition", "fautosave", "flinkrecord",
)


def publish_list_contract(env: dict, status: str = "C",
                          took: list | None = None) -> tuple[str | None, str | None, dict | None]:
    """发布/替换 botp_convertrule 的瘦列表 query 契约(upsert by urlformat)。

    请求参数 = 响应参数同款全集且全部可选(must=0):不传过滤即分页列全量,
    传 fsourcebill_number/ftargetbill_number/fname/fid 则按列过滤。
    返回 (api_id, error, urlformat)。
    """
    metadata = data.fetch_metadata(env, RULE_FORM)
    bill = dict(metadata.get("BillEntity") or {})
    keep = set(LIST_HEADER_FIELDS)
    bill["fields"] = [f for f in bill.get("fields", []) if f.get("name") in keep]
    missing = keep - {f.get("name") for f in bill["fields"]}
    if missing:
        raise RuntimeError(f"元数据缺少预期字段: {sorted(missing)}(平台版本变更?重跑调研)")
    bill["entries"] = []
    trimmed = {"BillEntity": bill}
    body = {"data": {
        "number": f"{RULE_FORM}_query",
        "name": f"{bill.get('displayname') or RULE_FORM}-查询",
        "httpmethod": "0",
        "urlformat": f"/v2/open/{RULE_FORM}/query",
        "apiservicetype": "0",
        "operation": "query",
        "bizobject_number": RULE_FORM,
        "appid_number": bill.get("bizAppNumber") or "botp",
        "version": "2",
        "enable": "1",
        "status": status,
    }}
    rows = data.build_save_body_entries(trimmed)
    for row in rows:  # 规则 A 已含 id 行;瘦列表契约里 id 与业务过滤参数全部可选
        if row.get("paramname") == "id":
            row["must"] = "0"
    body["data"]["bodyentryentity"] = rows
    body["data"]["respentryentity"] = data.resp_from_body(rows)
    body["data"]["filter_entity"] = json.loads(json.dumps(data.ID_FILTER))
    api_id, err = data._submit(env, "query", body, took or [])
    return api_id, err, body["data"]["urlformat"]


def query(env: dict, rule_id=None, source=None, target=None, name=None, fid=None,
          page_no: int = 1, page_size: int = 10) -> dict:
    """按可选过滤分页查询转换规则;返回苍穹 data(filter/rows/totalCount/...)。"""
    params = {"pageNo": str(page_no), "pageSize": str(page_size)}
    if rule_id:
        params["id"] = str(rule_id)
    if fid:
        params["fid"] = fid
    if name:
        params["fname"] = name
    if source:
        params["fsourcebill_number"] = source
    if target:
        params["ftargetbill_number"] = target
    t0 = time.time()
    body = ly_api.call(env, "GET", f"{QUERY_PATH}?{urllib.parse.urlencode(params)}")
    body["meta"] = {"took_ms": int((time.time() - t0) * 1000)}
    return body
