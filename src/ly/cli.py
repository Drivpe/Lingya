"""ly 命令行入口。

命令三层:
  ly auth      add/show/login/test/logout
  ly meta      devportal ai-meta 查询 + 元数据写(build-meta/modify-meta)
  ly api       任意端点透传兜底(lark-cli 模式)
所有输出走 JSON 信封(envelope)。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request

from . import __version__, api, auth, config, convert, data, settings
from .session import WebSession
from .envelope import fail, ok

# devportal ai-meta 端点表(来源: 灵基 app-build 技能 cosmic-meta-api 端点目录)
META_ENDPOINTS = {
    "get-dev-info":     ("/kapi/v2/devportal/ai-meta/getDevInfo", "GET"),
    "biz-apps":         ("/kapi/v2/devportal/ai-meta/bizApps", "GET"),
    "query-forms":      ("/kapi/v2/devportal/ai-meta/queryForms", "GET"),
    "query-forms-by-app": ("/kapi/v2/devportal/ai-meta/queryFormsByApp", "GET"),
    "form-schema":      ("/kapi/v2/devportal/ai-meta/getFormSchema", "GET"),
    "entity-type":      ("/kapi/v2/devportal/ai-meta/getEntityType", "GET"),
    "form-metadata":    ("/kapi/v2/devportal/ai-meta/getFormMetadata", "GET"),
    "form-config":      ("/kapi/v2/devportal/ai-meta/getFormConfig", "GET"),
    "entity-fields":    ("/kapi/v2/devportal/ai-meta/getEntityFields", "GET"),
}

# 元数据写端点(设计器建模通道),走写操作门
META_WRITES = {
    "build-meta":  "/kapi/v2/devportal/ai-meta/buildMeta",
    "modify-meta": "/kapi/v2/devportal/ai-meta/modifyMeta",
}


def _resolve_env(args) -> dict:
    try:
        return config.get_env(getattr(args, "env", None))
    except LookupError as e:
        fail("config", "no_env", str(e), "用 `ly auth add` 添加环境,或 `ly auth show` 查看已有环境")


def _unwrap(body, took_ms: int | None = None):
    """苍穹响应统一形状 {data,errorCode,message,status} → 信封。"""
    if not isinstance(body, dict):
        ok(body, meta={"took_ms": took_ms} if took_ms is not None else None)
    if str(body.get("errorCode", "0")) != "0" or body.get("status") is False:
        fail("api", body.get("errorCode"), body.get("message", "业务失败"))
    ok(body.get("data", body), meta={"took_ms": took_ms} if took_ms is not None else None)


# ── auth ──────────────────────────────────────────────────────────────────────

def cmd_auth(args) -> None:
    if args.auth_cmd == "add":
        if not args.url or not args.account_id or not args.client_id:
            fail("config", "missing", "--url/--account-id/--client-id 必填")
        config.save_env(args.name, {
            "url": args.url, "accountId": args.account_id,
            "client_id": args.client_id,
            "client_secret": args.client_secret or "",
            "username": args.username or "",
            "acgw": args.acgw or "",
            **({"normalAccessToken": True} if args.normal else {}),
            **({"isDefault": True} if args.default else {}),
        })
        ok({"name": args.name, "config": str(config.config_path())})
        return

    env = _resolve_env(args)
    if args.auth_cmd == "web-add":
        if not args.user or not args.password:
            fail("config", "missing", "--user/--password 必填")
        # 先验证能登录,再落盘(密码只存 ~/.kd/config.json,与 client-secret 同级)
        s = WebSession(env["url"], env["accountId"], args.user, args.password)
        s.login()
        config.save_env(env["name"], {"webUser": args.user, "webPassword": args.password})
        ok({"name": env["name"], "webUser": args.user, "verified": True,
            "config": str(config.config_path()),
            "hint": "convert-rule list/detail 将自动使用该凭证;撤销:重新 web-add 覆盖或手工删字段"})
        return
    if args.auth_cmd == "show":
        masked = {k: v for k, v in env.items() if k != "_raw"}
        if masked.get("client_secret"):
            s = masked["client_secret"]
            masked["client_secret"] = s[:4] + "…" + s[-4:] if len(s) > 10 else "…"
        if masked.get("acgw"):
            a = masked["acgw"]
            masked["acgw"] = a[:8] + "…"
        ok(masked)
    elif args.auth_cmd == "login":
        token = auth.get_token(env, force=True)
        ok({"token": token[:12] + "…(已缓存,不回显全文)", "url": env["url"]})
    elif args.auth_cmd == "test":
        token = auth.get_token(env)
        result = auth.verify_token(env, token)
        ok({"active": result.get("active"), "expires_in_ms": result.get("expires_in"),
            "scope": result.get("scope")})
    elif args.auth_cmd == "logout":
        auth.logout(env)
        ok({"cleared": True})


# ── meta ──────────────────────────────────────────────────────────────────────

def cmd_meta(args) -> None:
    env = _resolve_env(args)
    params = json.loads(args.params) if getattr(args, "params", None) else None
    if args.meta_cmd in META_WRITES:
        payload = json.loads(args.data) if args.data else None
        path = META_WRITES[args.meta_cmd]
        write_gate(env, "POST", path, payload, confirm=args.confirm, dry_run=args.dry_run)
        t0 = time.time()
        body = api.call(env, "POST", path, payload=payload)
        _unwrap(body, took_ms=int((time.time() - t0) * 1000))
        return
    if args.meta_cmd not in META_ENDPOINTS:
        fail("args", "unknown_endpoint",
             f"未知端点 {args.meta_cmd}(可选: {', '.join([*META_ENDPOINTS, *META_WRITES])})")
    path, method = META_ENDPOINTS[args.meta_cmd]
    t0 = time.time()
    body = api.call(env, method, path, payload=None, params=params)
    _unwrap(body, took_ms=int((time.time() - t0) * 1000))


# ── data(业务数据通道前置:precheck/publish) ─────────────────────────────────

def cmd_data(args) -> None:
    env = _resolve_env(args)
    form = args.form
    # save / query:已发布操作 API 的业务数据读写
    if args.data_cmd == "save":
        try:
            payload = json.loads(args.data) if args.data else None
        except json.JSONDecodeError as e:
            fail("args", "bad_json", f"--data 不是合法 JSON: {e}")
        if not isinstance(payload, dict):
            fail("args", "bad_data", "--data 必须是 JSON 对象(扁平业务字段)")
        wrapped = {"data": payload}
        path = f"/kapi/v2/open/{form}/save"
        write_gate(env, "POST", path, wrapped, confirm=args.confirm, dry_run=args.dry_run)
        t0 = time.time()
        body = api.call(env, "POST", path, payload=wrapped)
        if not body.get("status"):
            fail("api", body.get("errorCode"), body.get("message", "save 失败"),
                 "候选键语义:传 id=更新,不传=新增;字段名须与实体属性一致")
        d = body.get("data") or {}
        result = d.get("result") or []
        bill_id = result[0].get("id") if result and result[0].get("billStatus") else None
        ok({"billId": bill_id, "result": result,
            "successCount": d.get("successCount"), "failCount": d.get("failCount")},
           meta={"took_ms": int((time.time() - t0) * 1000),
                 "hint": f"读回: ly data query --form {form} --id {bill_id}" if bill_id else None})
    if args.data_cmd == "query":
        params = {"pageNo": str(args.page_no), "pageSize": str(args.page_size)}
        if args.id:
            params["id"] = str(args.id)
        if args.params:
            params.update(json.loads(args.params))
        path = f"/kapi/v2/open/{form}/query"
        t0 = time.time()
        body = api.call(env, "GET", f"{path}?{urllib.parse.urlencode(params)}")
        if not body.get("status"):
            fail("api", body.get("errorCode"), body.get("message", "query 失败"),
                 "query 发布契约必带 id+分页;字段集由发布时的返回参数定义固化")
        ok(body.get("data"), meta={"took_ms": int((time.time() - t0) * 1000)})

    # operate:已发布操作 API 的生命周期操作(submit/audit/unaudit/unsubmit/delete/push...)
    if args.data_cmd == "operate":
        params = {"id": str(args.id)}
        if args.params:
            params.update(json.loads(args.params))
        wrapped = {"data": params}
        path = f"/kapi/v2/open/{form}/{args.operation}"
        write_gate(env, "POST", path, wrapped, confirm=args.confirm, dry_run=args.dry_run)
        t0 = time.time()
        body = api.call(env, "POST", path, payload=wrapped)
        if not body.get("status"):
            fail("api", body.get("errorCode"), body.get("message", f"{args.operation} 失败"),
                 "状态迁移前置不满足或 id 不存在;操作 API 宽松语义:重复同向操作可能幂等成功")
        d = body.get("data") or {}
        result = d.get("result") or []
        errs = [e for r in result for e in (r.get("errors") or [])]
        ok({"operation": args.operation, "id": args.id,
            "successCount": d.get("successCount"), "totalCount": d.get("totalCount"),
            "failCount": d.get("failCount"), "result": result, "errors": errs},
           meta={"took_ms": int((time.time() - t0) * 1000),
                 "hint": "状态读回可用对向操作探测:audit 后 unaudit 成功即证处于已审核态"})

    if args.data_cmd == "precheck":
        checks, meta_info, operations, hints = [], {}, [], []
        body = api.call(env, "GET", f"/kapi/v2/devportal/ai-meta/queryForms?"
                                    f"{urllib.parse.urlencode({'keyword': form})}")
        forms = [f for f in (body.get("data") or [])
                 if isinstance(f, dict) and f.get("formNumber") == form] if body.get("status") else []
        checks.append({"check": "form_exists", "ok": bool(forms),
                       "detail": forms[0]["formId"] if forms else f"未找到表单 {form}"})
        try:
            metadata = data.fetch_metadata(env, form)
            bill = metadata.get("BillEntity", {})
            meta_info = {"bizAppNumber": bill.get("bizAppNumber", ""),
                         "displayname": bill.get("displayname", ""),
                         "headerFields": len(bill.get("fields", [])),
                         "entries": len(bill.get("entries", []))}
            checks.append({"check": "metadata", "ok": True, "detail": json.dumps(meta_info, ensure_ascii=False)})
        except Exception as e:  # noqa: BLE001 — precheck 把一切失败呈现为检查项
            checks.append({"check": "metadata", "ok": False, "detail": str(e)[:200]})
            hints.append("元数据不可取时无法发布操作 API;先确认表单编码与元数据完整性")
        try:
            ops = data.call_entity_operations(env, form)
            operations = ops
            detail = f"支持操作: {', '.join(ops)}" if ops else "getEntityOperations 返回空"
            checks.append({"check": "openapi_online", "ok": bool(ops), "detail": detail})
        except Exception as e:  # noqa: BLE001
            checks.append({"check": "openapi_online", "ok": False, "detail": str(e)[:200]})
            hints.append("开放平台服务不可达/未初始化:先在【开放服务云 → OpenAPI → 初始化】执行初始化,再重试")
        failed = [c for c in checks if not c["ok"]]
        ok({"checks": checks, "metadata": meta_info, "operations": operations,
            "hints": hints, "ready_to_publish": not failed},
           meta={"env": env["name"], "pass": not failed})
        return

    # publish
    operations = [op.strip() for op in (args.operations or "").split(",") if op.strip()]
    if not operations:
        fail("args", "missing_operations", "--operations 必填,如 save,query,submit,audit")
    preview = {"env": env["name"], "form": form, "operations": operations,
               "status": args.status,
               "endpoint": data.GEN_V2_API_PATH,
               "note": "upsert by urlformat(整体替换语义);将按 getEntityType 元数据自动构造三大子表"}
    write_gate(env, "POST", data.GEN_V2_API_PATH, preview,
               confirm=args.confirm, dry_run=args.dry_run)
    if args.dry_run:
        return
    try:
        metadata = data.fetch_metadata(env, form)
    except Exception as e:  # noqa: BLE001
        fail("metadata", "fetch_failed", str(e)[:300],
             "先跑 `ly data precheck --form <表单>` 看元数据检查项")
    bill = metadata.get("BillEntity", {})
    appid = args.appid or bill.get("bizAppNumber", "") or fail(
        "metadata", "no_app", "元数据缺 BizAppNumber,用 --appid 显式指定所属应用编码")
    prefix = args.prefix or bill.get("displayname", "") or form
    try:
        all_ops = data.call_entity_operations(env, form)
    except Exception as e:  # noqa: BLE001
        fail("openapi", "operations_failed", str(e)[:300])
    expanded = [op for op in operations if op in all_ops]
    skipped = [op for op in operations if op not in all_ops]
    if not expanded:
        fail("args", "unsupported_operations",
             f"实体不支持所请求操作;支持: {', '.join(all_ops)}")
    published, failed_list, took = [], [], []
    for op in expanded:
        qff = tuple(f.strip() for f in (getattr(args, "query_filter_fields", "") or "").split(",") if f.strip())
        api_id, err, urlformat = data.gen_api(env, form, appid, prefix, op, metadata,
                                              status=args.status, took=took,
                                              query_id_optional=getattr(args, "query_id_optional", False),
                                              query_filter_fields=qff)
        if api_id:
            published.append({"operation": op, "number": f"{form}_{op}",
                              "urlformat": urlformat, "apiId": api_id})
        else:
            failed_list.append({"operation": op, "error": err})
    ok({"published": published, "failed": failed_list, "skipped": skipped,
        "appid": appid, "name_prefix": prefix},
       meta={"took_ms": sum(took),
             "hint": "发布后用 GET /kapi/v2/<urlformat 去掉 /v2 前缀> 调用;"
                     "query 需带分页参数(如 pageNo=1&pageSize=10)"} if published else None)


def cmd_convert_rule(args) -> None:
    """ly convert-rule — BOTP 转换规则只读通道 v2(工单 #13;契约见 convert.py)。"""
    env = _resolve_env(args)
    web_user = getattr(args, "web_user", None)
    web_password = getattr(args, "web_password", None)
    if args.cr_cmd == "list":
        try:
            r = convert.list_paths(env, source=args.source, target=args.target,
                                   keyword=args.keyword,
                                   web_user=web_user, web_password=web_password)
        except Exception as e:  # noqa: BLE001 — 呈现为结构化错误信封
            fail("session", "list_failed", str(e)[:300],
                 "web 凭证缺失/错误:ly auth web-add --user <账号> --password <密码>")
        ok({"total_in_env": r["total_in_env"], "fetched": r["fetched"],
            "matched": r["matched"], "paths": r["paths"]},
           meta={"hint": "fetched≤500 为会话通道首屏上限;ruleId 获取用 detail 子命令或设计器规则树;"
                         "按 ruleId 读整行: ly convert-rule get --id <ruleId>"})
        return
    if args.cr_cmd == "get":
        body = convert.get_rule(env, args.id)
        ok(body, meta={"hint": "字段映射/值转换等策略明细: detail 子命令(会话通道)"})
        return
    # detail
    try:
        raw_pid = convert.first_path_detail(env, web_user=web_user, web_password=web_password)
    except Exception as e:  # noqa: BLE001
        fail("session", "detail_failed", str(e)[:300],
             "web 凭证缺失/错误:ly auth web-add --user <账号> --password <密码>")
    ok(raw_pid, meta={"hint": "detail 当前固定打开路线列表第一行(网格选中态传输格式待破解,见 issue #13);"
                             "rules[].rule_id 可直接用于 ly convert-rule get --id"})


# ── 写操作门(confirm 模式:非 GET 一律先预览,--confirm 才执行) ─────────────
def write_gate(env: dict, method: str, path: str, payload, params=None,
               confirm: bool = False, dry_run: bool = False) -> None:
    """write-mode=confirm 时,非 GET 请求默认 dry-run;--confirm 放行。

    free 模式直接放行;--dry-run 在任何模式下都只看预览。
    """
    preview = {
        "mode": "dry-run(未执行)",
        "write_mode": settings.get_write_mode(),
        "env": env["name"],
        "method": method.upper(),
        "path": path,
        "body": payload,
        "params": params,
    }
    if dry_run:
        ok(preview)
    if settings.get_write_mode() == "confirm" and not confirm:
        ok(preview, meta={"hint": "write-mode=confirm:确认无误后加 --confirm 执行;或 ly config set write-mode free 永久放开"})


# ── api 透传 ──────────────────────────────────────────────────────────────────

def cmd_api(args) -> None:
    env = _resolve_env(args)
    t0 = time.time()
    # Git Bash/MSYS 会把 /kapi/... 改写成 Windows 路径(如 C:/Program Files/Git/kapi/...);尽力还原
    path = args.path.replace("\\", "/")
    if len(path) > 2 and path[1] == ":":
        m = re.search(r"/Git/(.+)$", path)
        path = "/" + m.group(1).lstrip("/") if m else "/" + path.split(":/", 1)[-1].lstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    args.path = path
    payload = json.loads(args.data) if args.data else None
    if args.method.upper() != "GET":
        write_gate(env, args.method.upper(), args.path, payload,
                   params=json.loads(args.params) if args.params else None,
                   confirm=args.confirm, dry_run=args.dry_run)
    params = json.loads(args.params) if args.params else None
    body = api.call(env, args.method.upper(), args.path,
                    payload=payload, params=params, style=args.style)
    _unwrap(body, took_ms=int((time.time() - t0) * 1000))


# ── config(ly 自有设置) ─────────────────────────────────────────────────────

def cmd_config(args) -> None:
    if args.config_cmd == "show":
        ok({"write_mode": settings.get_write_mode(),
            "settings_file": str(settings.settings_path())})
    elif args.config_cmd == "set":
        try:
            settings.set_write_mode(args.value)
        except ValueError as e:
            fail("args", "bad_value", str(e))
        ok({"write_mode": settings.get_write_mode()})


# ── doctor ────────────────────────────────────────────────────────────────────

def cmd_doctor(args) -> None:
    checks: list[dict] = []
    cfg = config.load()
    names = config.env_names(cfg)
    checks.append({"check": "config", "ok": bool(cfg), "detail": str(config.config_path())})
    if not names:
        fail("doctor", "no_env", "没有任何环境配置", "ly auth add --name X --url ... --account-id ... --client-id ...")
    env = config.get_env(args.env)
    checks.append({"check": "env", "ok": True, "detail": f"{env['name']} -> {env['url']}"})
    missing = [k for k in ("accountId", "client_id", "client_secret") if not env[k]]
    checks.append({"check": "credentials", "ok": not missing, "detail": "缺失: " + ",".join(missing) if missing else "齐全"})
    try:
        urllib.request.urlopen(env["url"] + "/login.html", timeout=8)
        checks.append({"check": "reachable", "ok": True, "detail": env["url"]})
    except Exception as e:  # noqa: BLE001 — doctor 要把任何网络问题呈现为检查项而非崩溃
        checks.append({"check": "reachable", "ok": False, "detail": str(e)})
    if not missing:
        try:
            token = auth.get_token(env, force=True)
            checks.append({"check": "getToken", "ok": True, "detail": token[:12] + "…"})
            v = auth.verify_token(env, token)
            checks.append({"check": "verifyToken", "ok": bool(v.get("active")),
                           "detail": f"expires_in={v.get('expires_in')}ms"})
        except auth.AuthError as e:
            checks.append({"check": "getToken", "ok": False,
                           "detail": f"[{e.code}] {e}(注意: 服务端有密钥错误锁定,勿连续重试)"})
    failed = [c for c in checks if not c["ok"]]
    ok(checks, meta={"env": env["name"], "pass": not failed})


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ly", description="Lingya 个人金蝶 ERP 开发 CLI")
    p.add_argument("--version", action="version", version=f"ly {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("-e", "--env", help="环境名(默认取 isDefault/第一个)")

    auth_p = sub.add_parser("auth", help="环境与认证")
    auth_sub = auth_p.add_subparsers(dest="auth_cmd", required=True)
    add_p = auth_sub.add_parser("add", help="添加/更新环境(写 ~/.kd/config.json,与灵基环境管理同源)")
    add_p.add_argument("--name", required=True)
    add_p.add_argument("--url", required=True, help="环境根地址,如 http://127.0.0.1:8080/ierp")
    add_p.add_argument("--account-id", required=True)
    add_p.add_argument("--client-id", required=True)
    add_p.add_argument("--client-secret", default="")
    add_p.add_argument("--username", default="")
    add_p.add_argument("--acgw", default="", help="网关标识 x-acgw-identity")
    add_p.add_argument("--normal", action="store_true", help="normal 两步认证(getAppToken.do+login.do)")
    add_p.add_argument("--default", action="store_true")
    for name in ("show", "login", "test", "logout"):
        sp = auth_sub.add_parser(name)
        common(sp)
    webadd_p = auth_sub.add_parser("web-add", help="存 Web 会话凭证(设计器通道:账号+密码,先验证后落盘)")
    webadd_p.add_argument("--user", required=True, help="Web 登录账号(手机号/用户名)")
    webadd_p.add_argument("--password", required=True, help="Web 登录密码")
    common(webadd_p)
    auth_p.set_defaults(func=cmd_auth)

    meta_p = sub.add_parser("meta", help="devportal 元数据查询与写")
    meta_sub = meta_p.add_subparsers(dest="meta_cmd", required=True)
    for name, (path, method) in META_ENDPOINTS.items():
        sp = meta_sub.add_parser(name)
        sp.add_argument("--params", help='查询参数 JSON,如 \'{"keyword":"BAS"}\'')
        common(sp)
    for name in META_WRITES:
        sp = meta_sub.add_parser(name, help=f"元数据写: {META_WRITES[name]}(走写操作门)")
        sp.add_argument("--data", help='请求体 JSON,如 buildMeta 的需求产物 / modifyMeta 的 MetaOps')
        sp.add_argument("--confirm", action="store_true",
                        help="write-mode=confirm 时,真执行必须携带")
        sp.add_argument("--dry-run", action="store_true", help="只打印请求预览,不执行")
        common(sp)
    meta_p.set_defaults(func=cmd_meta)

    api_p = sub.add_parser("api", help="任意端点透传(兜底层)")
    api_p.add_argument("method", choices=["GET", "POST", "PUT", "DELETE"])
    api_p.add_argument("path")
    api_p.add_argument("--data", help="请求体 JSON")
    api_p.add_argument("--params", help="查询参数 JSON")
    api_p.add_argument("--style", choices=["kapi", "legacy"], default="kapi")
    api_p.add_argument("--confirm", action="store_true",
                       help="write-mode=confirm 时,真执行非 GET 请求必须携带")
    api_p.add_argument("--dry-run", action="store_true", help="只打印请求预览,不执行")
    common(api_p)
    api_p.set_defaults(func=cmd_api)

    cfg_p = sub.add_parser("config", help="ly 自有设置(~/.ly/config.json)")
    cfg_sub = cfg_p.add_subparsers(dest="config_cmd", required=True)
    cfg_sub.add_parser("show", help="查看当前设置")
    set_p = cfg_sub.add_parser("set", help="设置项,如:ly config set write-mode free")
    set_p.add_argument("key", choices=["write-mode"])
    set_p.add_argument("value", choices=["confirm", "free"])
    cfg_p.set_defaults(func=cmd_config)

    data_p = sub.add_parser("data", help="业务数据通道前置:precheck/publish(开放平台 v2 操作 API)")
    data_sub = data_p.add_subparsers(dest="data_cmd", required=True)
    pre_p = data_sub.add_parser("precheck", help="四项检查:表单存在/元数据可取/操作可查/开放平台在线")
    pre_p.add_argument("--form", required=True, help="表单/实体编码,如 ly_test_bill_a1")
    common(pre_p)
    pre_p.set_defaults(func=cmd_data)
    pub_p = data_sub.add_parser("publish", help="按元数据自动构造并注册 v2 操作 API(走写操作门)")
    pub_p.add_argument("--form", required=True, help="表单/实体编码")
    pub_p.add_argument("--operations", required=True,
                       help='逗号分隔,如 "save,query,submit,audit"(query 生成 GET 查询 API)')
    pub_p.add_argument("--appid", default=None, help="所属应用编码(默认取元数据 BizAppNumber)")
    pub_p.add_argument("--prefix", default=None, help="API 名称前缀(默认取实体中文名)")
    pub_p.add_argument("--status", default="C", choices=["A", "B", "C", "D"],
                       help="API 状态:A=内测/B=维护/C=发布/D=禁用,默认 C")
    pub_p.add_argument("--query-id-optional", action="store_true",
                       help="query 契约的 id 改为可选(默认必填):同契约兼得分页列全量能力;"
                            "对已发布 API 重发即整体替换(upsert by urlformat)")
    pub_p.add_argument("--query-filter-fields", default=None,
                       help="query 契约追加可选过滤参数(逗号分隔元数据头部字段名,如 number,name,enabled),"
                            "供 ly data query --params 使用")
    pub_p.add_argument("--confirm", action="store_true",
                       help="write-mode=confirm 时,真执行必须携带")
    pub_p.add_argument("--dry-run", action="store_true", help="只打印请求预览,不执行")
    common(pub_p)
    pub_p.set_defaults(func=cmd_data)
    save_p = data_sub.add_parser("save", help="调已发布 save API 写入业务数据(走写操作门)")
    save_p.add_argument("--form", required=True, help="表单/实体编码")
    save_p.add_argument("--data", required=True,
                        help='业务字段 JSON(扁平),如 \'{"title":"x","qty":5}\';传 id=更新,不传=新增')
    save_p.add_argument("--confirm", action="store_true", help="write-mode=confirm 时,真执行必须携带")
    save_p.add_argument("--dry-run", action="store_true", help="只打印请求预览,不执行")
    common(save_p)
    save_p.set_defaults(func=cmd_data)
    qry_p = data_sub.add_parser("query", help="调已发布 query API 读回业务数据")
    qry_p.add_argument("--form", required=True, help="表单/实体编码")
    qry_p.add_argument("--id", default=None, help="按单据 id 精确查(发布契约必带)")
    qry_p.add_argument("--page-no", default=1)
    qry_p.add_argument("--page-size", default=10)
    qry_p.add_argument("--params", help='额外查询参数 JSON,如 \'{"title":"x"}\'(须在发布契约内)')
    common(qry_p)
    qry_p.set_defaults(func=cmd_data)
    op_p = data_sub.add_parser("operate", help="调已发布操作 API 执行生命周期动作(submit/audit/unaudit/unsubmit/delete)")
    op_p.add_argument("--form", required=True, help="表单/实体编码")
    op_p.add_argument("--operation", required=True,
                      help="操作名=已发布 API 的 operation,如 submit/audit/unaudit/unsubmit/delete")
    op_p.add_argument("--id", required=True, help="目标单据 id")
    op_p.add_argument("--params", help='附加查询条件 JSON,合并进 data')
    op_p.add_argument("--confirm", action="store_true", help="write-mode=confirm 时,真执行必须携带")
    op_p.add_argument("--dry-run", action="store_true", help="只打印请求预览,不执行")
    common(op_p)
    op_p.set_defaults(func=cmd_data)

    cr_p = sub.add_parser("convert-rule",
                          help="单据转换(BOTP)规则只读通道:list(路线)/get(按ruleId)/detail(详情)")
    cr_sub = cr_p.add_subparsers(dest="cr_cmd", required=True)
    crls_p = cr_sub.add_parser("list", help="列环境内转换路线(会话通道;源单/目标单/关键词客户端过滤)")
    crls_p.add_argument("--source", help="源单编码精确过滤,如 ly_test_bill_a1")
    crls_p.add_argument("--target", help="目标单编码精确过滤")
    crls_p.add_argument("--keyword", help="关键词子串过滤(匹配源/目标编码与名称)")
    crls_p.add_argument("--web-user", default=None, help="临时 web 账号(默认读环境配置 webUser/loginUser)")
    crls_p.add_argument("--web-password", default=None, help="临时 web 密码(默认读环境配置 webPassword)")
    common(crls_p)
    crls_p.set_defaults(func=cmd_convert_rule)
    crget_p = cr_sub.add_parser("get", help="按数字主键(ruleId)读规则整行(OpenAPI 通道)")
    crget_p.add_argument("--id", required=True, help="ruleId(rows[].id,数字主键)")
    common(crget_p)
    crget_p.set_defaults(func=cmd_convert_rule)
    crd_p = cr_sub.add_parser("detail", help="会话通道打开规则详情(当前固定第一行),解析规则树/字段值/映射网格")
    crd_p.add_argument("--web-user", default=None)
    crd_p.add_argument("--web-password", default=None)
    common(crd_p)
    crd_p.set_defaults(func=cmd_convert_rule)

    doc_p = sub.add_parser("doctor", help="环境体检:配置→连通→认证")
    common(doc_p)
    doc_p.set_defaults(func=cmd_doctor)
    return p


def main(argv=None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except auth.AuthError as e:
        fail("auth", e.code, str(e), "检查 client_secret 是否已保存生效;限流 30次/分,勿连续重试")
    except api.ApiError as e:
        fail("api", e.code, str(e))
    except LookupError as e:
        fail("config", "no_env", str(e))
    except KeyboardInterrupt:
        fail("interrupted", "sigint", "用户中断")


if __name__ == "__main__":
    main()
