"""JSON 信封输出契约。

成功: stdout {"ok":true,"data":...,"meta":{...}},退出码 0
失败: stderr {"ok":false,"error":{type,code,message,hint}},退出码非 0
agent 只判 ok / 退出码,不判业务码。
"""

from __future__ import annotations

import json
import sys

# Windows 管道默认 GBK,会把中文 JSON 变乱码;信封契约固定 UTF-8
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")


def ok(data=None, meta: dict | None = None) -> None:
    payload: dict = {"ok": True, "data": data}
    if meta:
        payload["meta"] = meta
    json.dump(payload, sys.stdout, ensure_ascii=False, default=str)
    sys.stdout.write("\n")
    raise SystemExit(0)


def fail(err_type: str, code, message: str, hint: str = "") -> None:
    payload = {
        "ok": False,
        "error": {"type": err_type, "code": code, "message": message, "hint": hint},
    }
    json.dump(payload, sys.stderr, ensure_ascii=False, default=str)
    sys.stderr.write("\n")
    raise SystemExit(1)
