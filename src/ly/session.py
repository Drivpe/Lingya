"""ly session — 苍穹 Web 会话通道(设计器通用表单服务)。

为什么存在:苍穹设计器页面(含【单据转换管理】)不走 OpenAPI,走会话 Cookie +
通用表单服务(调研 docs/research-转换规则端点契约调研.md §8):
  1. 登录三步:auth/queryParameters.do → auth/getPublicKey.do(RSA 公钥)
              → auth/yzjlogin.do(useraccount + RSA(PKCS#1 v1.5) 加密 password)
  2. 表单页面会话:GET form/getConfig.do(响应含服务端下发的 pageId)
  3. 动作通道:POST form/batchInvokeAction.do(body: pageId=&appId=bos&params=[...])
     pageId 是会话钥匙,自造 pageId 会被拒("当前表单会话超时")。

纯标准库:RSA 用手写 PKCS#1 v1.5(modexp);DER 公钥解析用手写最小 ASN.1 读取器。
凭证红线:web 密码只存 ~/.kd/config.json(与 client-secret 同级),永不入仓/入日志。
"""

from __future__ import annotations

import base64
import hashlib
import http.cookiejar
import json
import os
import random
import re
import string
import time
import urllib.error
import urllib.parse
import urllib.request


class SessionError(RuntimeError):
    """会话通道错误(登录失败/页面会话失效等)。"""


# ── 最小 DER/ASN.1 读取(RSAPublicKey 提取) ──────────────────────────────────
def _der_read(buf: bytes, off: int) -> tuple[int, bytes, int]:
    """读一个 TLV;返回 (tag, value, next_off)。只支持本场景用到的短/长长度形式。"""
    tag = buf[off]
    off += 1
    ln = buf[off]
    off += 1
    if ln & 0x80:
        n = ln & 0x7F
        ln = int.from_bytes(buf[off:off + n], "big")
        off += n
    return tag, buf[off:off + ln], off + ln


def _rsa_from_der_spki(spki_b64: str) -> tuple[int, int]:
    """SubjectPublicKeyInfo(BASE64 DER) → (n, e)。"""
    data = base64.b64decode(spki_b64)
    _, inner, _ = _der_read(data, 0)                 # SEQUENCE
    _, alg, off2 = _der_read(inner, 0)               # AlgorithmIdentifier(丢弃)
    _, bitstr, _ = _der_read(inner, off2)            # BIT STRING
    if bitstr[0] != 0:
        raise SessionError("公钥 BIT STRING 格式异常")
    _, seq, _ = _der_read(bitstr, 1)                 # RSAPublicKey SEQUENCE
    _, n_bytes, off3 = _der_read(seq, 0)
    _, e_bytes, _ = _der_read(seq, off3)
    return int.from_bytes(n_bytes, "big"), int.from_bytes(e_bytes, "big")


def rsa_encrypt_pkcs1(plaintext: str, spki_b64: str) -> str:
    """PKCS#1 v1.5 加密,cost: 纯 stdlib(modexp)。返回 base64。"""
    n, e = _rsa_from_der_spki(spki_b64)
    k = (n.bit_length() + 7) // 8
    data = plaintext.encode("utf-8")
    if len(data) > k - 11:
        raise SessionError("密码长度超出 RSA 单块上限")
    pad_len = k - 3 - len(data)
    padding = bytes(random.choice([b for b in range(1, 256)]) for _ in range(pad_len))
    em = b"\x00\x02" + padding + b"\x00" + data
    m = int.from_bytes(em, "big")
    c = pow(m, e, n)
    return base64.b64encode(c.to_bytes(k, "big")).decode()


# ── 会话 ─────────────────────────────────────────────────────────────────────
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) ly-cli-session "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36")


def _rand(n: int = 16) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


class WebSession:
    """苍穹 Web 会话:登录 + 通用表单服务客户端。非线程安全,一环境一实例。"""

    def __init__(self, base_url: str, account_id: str, user: str, password: str):
        self.base = base_url.rstrip("/")
        self.account_id = account_id
        self.user = user
        self.password = password
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))
        self._logged_in = False

    # ── http 小工具 ──
    def _get(self, path: str, qs: str = "") -> str:
        url = f"{self.base}/{path.lstrip('/')}" + (f"?{qs}" if qs else "")
        req = urllib.request.Request(url, headers={"User-Agent": _UA,
                                                   "X-Requested-With": "XMLHttpRequest"})
        try:
            with self.opener.open(req, timeout=60) as resp:
                return resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            raise SessionError(f"GET {path} HTTP {e.code}: {e.read()[:200]}") from e

    def _post_form(self, path: str, qs: str, body: dict,
                   extra_headers: dict | None = None) -> str:
        url = f"{self.base}/{path.lstrip('/')}" + (f"?{qs}" if qs else "")
        data = urllib.parse.urlencode(body).encode()
        headers = {"User-Agent": _UA, "X-Requested-With": "XMLHttpRequest",
                   "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
        headers.update(extra_headers or {})
        req = urllib.request.Request(url, data=data, headers=headers)
        try:
            with self.opener.open(req, timeout=120) as resp:
                return resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            raise SessionError(f"POST {path} HTTP {e.code}: {e.read()[:200]}") from e

    # ── 登录三步(§8.1) ──
    def login(self) -> None:
        self._get("auth/queryParameters.do",
                  urllib.parse.urlencode({"accountId": self.account_id, "language": "zh_CN"}))
        access_key = f"{self.user}BOS{''.join(random.choices(string.ascii_letters, k=2))}"
        pk_resp = json.loads(self._post_form(
            "auth/getPublicKey.do", "",
            {"accessKey": access_key, "language": "zh_CN", "accountId": self.account_id}))
        public_key = pk_resp.get("publicKey") or ""
        if not public_key:
            raise SessionError(f"getPublicKey 未返回公钥: {str(pk_resp)[:200]}")
        enc = rsa_encrypt_pkcs1(self.password, public_key)
        login_resp = json.loads(self._post_form(
            "auth/yzjlogin.do", "",
            {"type": "user", "userSourceType": "2", "accountId": self.account_id,
             "language": "zh_CN", "useraccount": self.user, "password": enc,
             "accessKey": access_key}))
        if login_resp.get("errorcode"):
            raise SessionError(
                f"登录失败: {login_resp.get('description') or login_resp.get('errorcode')}")
        self._logged_in = True

    def ensure_login(self) -> None:
        if not self._logged_in:
            self.login()

    # ── 通用表单服务(§8.1) ──
    def open_form(self, form_number: str) -> str:
        """getConfig 建立表单页面会话;返回服务端下发的 pageId。"""
        self.ensure_login()
        params = json.dumps({"formId": form_number, "flag": _rand(), "f": _rand()},
                            ensure_ascii=False)
        qs = urllib.parse.urlencode({"params": params, "random": random.random()})
        cfg = json.loads(self._get("form/getConfig.do", qs))
        page_id = cfg.get("pageId") or ""
        if not page_id:
            raise SessionError(f"getConfig 未下发 pageId(form={form_number})")
        return page_id

    def invoke(self, form_number: str, action: str, page_id: str,
               params: list) -> list:
        """batchInvokeAction:返回动作指令流 [{'a':..,'p':..}]。"""
        out = self.raw_invoke(form_number, action, page_id, params)
        try:
            return json.loads(out)
        except json.JSONDecodeError as e:
            raise SessionError(f"动作响应非 JSON(ac={action}): {out[:200]}") from e

    @staticmethod
    def _csrf_headers(params_json: str) -> dict:
        """构造 batchInvokeAction/invokeAction 的防重放三头(FormAction.checkCsrf 逆向)。

        服务端只做自洽校验,不验 token 值:
          signature = sha256hex(client-start-time + kd-csrf-token + tail + params[:min(len,300)]) + tail
        payload 超过 300 字符时,signature 以 "<hex>__length__<maxlen>" 形式声明截断长度。
        """
        start = str(int(time.time() * 1000))
        token = _rand(16)
        tail = _rand(16)
        n = min(len(params_json), 300)
        digest = hashlib.sha256(
            (start + token + tail + params_json[:n]).encode("utf-8")).hexdigest()
        signature = digest + tail
        if len(params_json) > 300:
            signature += f"__length__{len(params_json)}"
        return {"client-start-time": start, "kd-csrf-token": token, "signature": signature}

    def raw_invoke(self, form_number: str, action: str, page_id: str,
                   params: list) -> str:
        qs = urllib.parse.urlencode({"appId": "bos", "f": form_number, "ac": action})
        params_json = json.dumps(params, ensure_ascii=False)
        body = {"pageId": page_id, "appId": "bos", "params": params_json}
        out = self._post_form("form/batchInvokeAction.do", qs, body,
                              extra_headers=self._csrf_headers(params_json))
        if "当前表单会话超时" in out:
            raise SessionError("表单页面会话失效(pageId 过期),请重新 open_form")
        return out

    def find_session_cookie(self) -> str:
        """调试用:返回会话 cookie 的 name=value 首对(不落文档)。"""
        for c in self.jar:
            return f"{c.name}=<omitted>"
        return "<no-cookie>"
