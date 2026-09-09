"""增强型 Token 认证(/kapi/oauth2/*)。

规范来源: 金蝶AI苍穹OpenAPI增强型Token认证(vip.kingdee.com/knowledge/489812471545485056)
- getToken: client_id/client_secret/username/accountId/nonce/timestamp → access_token(2h)
- verifyToken / withdrawToken
- 限流 1分钟30次;密钥错误有锁定机制,禁止连续硬试
"""

from __future__ import annotations

import json
import secrets
import time
from datetime import datetime
from pathlib import Path

import urllib.error
import urllib.request

from . import config

TOKEN_DIR = Path.home() / ".ly"


class AuthError(RuntimeError):
    def __init__(self, code, message, trace_id=""):
        super().__init__(message)
        self.code = code
        self.trace_id = trace_id


def _nonce() -> str:
    return f"{secrets.randbelow(10**12):012d}"


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _headers(env: dict, extra: dict | None = None) -> dict:
    h = {"Content-Type": "application/json"}
    if env.get("acgw"):
        h["x-acgw-identity"] = env["acgw"]
    if extra:
        h.update(extra)
    return h


def _post(env: dict, path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        env["url"] + path,
        data=json.dumps(payload).encode("utf-8"),
        headers=_headers(env),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        if e.code == 401:
            # SKILL 铁律 4:401=密钥错误/被锁。服务端有密钥错误锁定,连续重试会加重锁定。
            raise AuthError("auth_locked_or_bad_secret",
                            "getToken 401:应用密钥(client_secret)错误或已被锁定;"
                            "请核对密钥后重试,勿连续重试(限流 30 次/分,错误会触发锁定)") from e
        raise AuthError(e.code, f"HTTP {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise AuthError("network", f"连接失败 {env['url']}: {e.reason}") from e
    if str(body.get("errorCode", "0")) != "0" or body.get("status") is False:
        raise AuthError(body.get("errorCode"), body.get("message", "认证失败"))
    return body


def _cache_path(env: dict) -> Path:
    return TOKEN_DIR / f"token-{env['name']}.json"


def _load_cache(env: dict) -> str:
    p = _cache_path(env)
    if not p.is_file():
        return ""
    try:
        c = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if c.get("url") != env["url"] or c.get("client_id") != env["client_id"]:
        return ""
    if float(c.get("expires_at", 0)) - 300 <= time.time():  # 提前 5 分钟视为过期
        return ""
    return str(c.get("access_token", ""))


def _save_cache(env: dict, token: str, expires_in_ms) -> None:
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    expires_at = time.time() + float(expires_in_ms or 7_200_000) / 1000
    _cache_path(env).write_text(
        json.dumps({"access_token": token, "expires_at": expires_at,
                    "url": env["url"], "client_id": env["client_id"]}),
        encoding="utf-8",
    )


def get_token(env: dict, force: bool = False) -> str:
    if not force:
        cached = _load_cache(env)
        if cached:
            return cached
    if not (env["url"] and env["client_id"] and env["client_secret"] and env["accountId"]):
        raise AuthError("config", "环境配置不完整",
                        "需要 url/accountId/client_id/client_secret;用 `ly auth add` 补齐")
    body = _post(env, "/kapi/oauth2/getToken", {
        "username": env["username"],
        "client_id": env["client_id"],
        "client_secret": env["client_secret"],
        "accountId": env["accountId"],
        "language": "zh_CN",
        "nonce": _nonce(),
        "timestamp": _timestamp(),
    })
    data = body.get("data") or {}
    token = str(data.get("access_token") or "").strip()
    if not token:
        raise AuthError("empty", "getToken 成功但未返回 access_token")
    _save_cache(env, token, data.get("expires_in"))
    return token


def verify_token(env: dict, token: str) -> dict:
    body = _post(env, "/kapi/oauth2/verifyToken", {
        "client_id": env["client_id"],
        "token_type_hint": "access_token",
        "token": token,
        "accountId": env["accountId"],
        "nonce": _nonce(),
        "timestamp": _timestamp(),
    })
    return body.get("data") or {}


def withdraw_token(env: dict, token: str) -> None:
    _post(env, "/kapi/oauth2/withdrawToken", {
        "client_id": env["client_id"],
        "client_secret": env["client_secret"],
        "token_type_hint": "access_token",
        "token": token,
        "accountId": env["accountId"],
        "nonce": _nonce(),
        "timestamp": _timestamp(),
    })


def logout(env: dict) -> None:
    """撤回缓存中的 token 并清缓存(失败不阻塞——token 可能已过期)。"""
    token = _load_cache(env)
    if token:
        try:
            withdraw_token(env, token)
        except AuthError:
            pass
    _cache_path(env).unlink(missing_ok=True)
