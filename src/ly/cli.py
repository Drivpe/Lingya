"""ly 命令行入口。

命令三层:
  ly auth      add/show/login/test/logout
  ly meta      devportal ai-meta 只读查询(getDevInfo/bizApps/queryForms/...)
  ly api       任意端点透传兜底(lark-cli 模式)
所有输出走 JSON 信封(envelope)。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request

from . import __version__, api, auth, config, settings
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


def _resolve_env(args) -> dict:
    try:
        return config.get_env(getattr(args, "env", None))
    except LookupError as e:
        fail("config", "no_env", str(e), "用 `ly auth add` 添加环境,或 `ly auth show` 查看已有环境")


def _unwrap(body):
    """苍穹响应统一形状 {data,errorCode,message,status} → 信封。"""
    if not isinstance(body, dict):
        ok(body)
    if str(body.get("errorCode", "0")) != "0" or body.get("status") is False:
        fail("api", body.get("errorCode"), body.get("message", "业务失败"))
    ok(body.get("data", body))


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
    if args.meta_cmd not in META_ENDPOINTS:
        fail("args", "unknown_endpoint", f"未知端点 {args.meta_cmd}(可选: {', '.join(META_ENDPOINTS)})")
    path, method = META_ENDPOINTS[args.meta_cmd]
    env = _resolve_env(args)
    params = json.loads(args.params) if args.params else None
    t0 = time.time()
    body = api.call(env, method, path, payload=None, params=params)
    _unwrap(body)


# ── 写操作门(confirm 模式:非 GET 一律先预览,--confirm 才执行) ─────────────

def write_gate(args, env: dict, payload) -> None:
    """write-mode=confirm 时,非 GET 请求默认 dry-run;--confirm 放行。

    free 模式直接放行;--dry-run 在任何模式下都只看预览。
    """
    preview = {
        "mode": "dry-run(未执行)",
        "write_mode": settings.get_write_mode(),
        "env": env["name"],
        "method": args.method.upper(),
        "path": args.path,
        "body": payload,
        "params": getattr(args, "params", None),
    }
    if getattr(args, "dry_run", False):
        ok(preview)
    if settings.get_write_mode() == "confirm" and not getattr(args, "confirm", False):
        ok(preview, meta={"hint": "write-mode=confirm:确认无误后加 --confirm 执行;或 ly config set write-mode free 永久放开"})


# ── api 透传 ──────────────────────────────────────────────────────────────────

def cmd_api(args) -> None:
    env = _resolve_env(args)
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
        write_gate(args, env, payload)
    params = json.loads(args.params) if args.params else None
    body = api.call(env, args.method.upper(), args.path,
                    payload=payload, params=params, style=args.style)
    _unwrap(body)


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
    auth_p.set_defaults(func=cmd_auth)

    meta_p = sub.add_parser("meta", help="devportal 元数据只读查询")
    meta_sub = meta_p.add_subparsers(dest="meta_cmd", required=True)
    for name in META_ENDPOINTS:
        sp = meta_sub.add_parser(name)
        sp.add_argument("--params", help='查询参数 JSON,如 \'{"keyword":"BAS"}\'')
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
