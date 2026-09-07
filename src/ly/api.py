"""OpenAPI 调用层:kapi 风格(accessToken 头)与 legacy 风格(access_token 头 + api:true)。"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from . import auth


class ApiError(RuntimeError):
    def __init__(self, code, message, trace_id="", http_status=None):
        super().__init__(message)
        self.code = code
        self.trace_id = trace_id
        self.http_status = http_status


def _headers(env: dict, token: str, style: str, content_type: str | None) -> dict:
    h = {}
    if env.get("acgw"):
        h["x-acgw-identity"] = env["acgw"]
    if style == "kapi":
        h["accessToken"] = token
        if content_type:
            h["Content-Type"] = content_type
    else:  # legacy_api
        h["access_token"] = token
        h["accesstoken"] = token
        h["api"] = "true"
        if content_type:
            h["Content-Type"] = content_type
    return h


def _is_body_401(body) -> bool:
    """苍穹常见:HTTP 200 + 业务 errorCode 401(token 失效/未授权)。"""
    return isinstance(body, dict) and str(body.get("errorCode")) == "401"


def call(env: dict, method: str, path: str, payload: dict | None = None,
         params: dict | None = None, style: str = "kapi",
         _retried: bool = False) -> dict:
    token = auth.get_token(env)
    url = env["url"] + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url, data=data,
        headers=_headers(env, token, style, "application/json" if data else None),
        method=method.upper(),
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code == 401 and not _retried:
            return call(env, method, path, payload, params, style, _retried=True)
        detail = e.read().decode("utf-8", "replace")[:300]
        raise ApiError(e.code, f"HTTP {e.code}: {detail}", http_status=e.code) from e
    try:
        body = json.loads(raw)
    except ValueError:
        body = raw
    if _is_body_401(body) and not _retried:
        return call(env, method, path, payload, params, style, _retried=True)
    return body
