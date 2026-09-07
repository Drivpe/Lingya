"""环境配置:与灵基客户端「环境管理」同源,读 ~/.kd/config.json 的 env 段。"""

from __future__ import annotations

import json
import os
from pathlib import Path

_MISSING = object()


def config_path() -> Path:
    return Path(os.environ.get("LY_CONFIG", "")) if os.environ.get("LY_CONFIG") else Path.home() / ".kd" / "config.json"


def load() -> dict:
    p = config_path()
    if not p.is_file():
        return {}
    with p.open("r", encoding="utf-8-sig") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def env_names(cfg: dict | None = None) -> list[str]:
    cfg = cfg if cfg is not None else load()
    env = cfg.get("env")
    if isinstance(env, dict):
        return [k for k, v in env.items() if isinstance(v, dict)]
    if isinstance(env, list):
        return [str(e.get("name", f"env_{i}")) for i, e in enumerate(env) if isinstance(e, dict)]
    return []


def _pick(d: dict, *keys: str) -> str:
    for k in keys:
        v = d.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def get_env(name: str | None = None) -> dict:
    """按名字取环境;未指定时取 isDefault,否则第一个。字段名做 camel/snake 兼容归一。"""
    cfg = load()
    envs = cfg.get("env")
    entries: dict[str, dict] = {}
    if isinstance(envs, dict):
        entries = {k: v for k, v in envs.items() if isinstance(v, dict)}
    elif isinstance(envs, list):
        entries = {
            (str(e.get("name", "")).strip() or f"env_{i}"): e
            for i, e in enumerate(envs)
            if isinstance(e, dict)
        }
    if not entries:
        raise LookupError("config 中没有任何环境;先用 `ly auth add` 添加")
    key = name or next((k for k, v in entries.items() if _is_default(v)), next(iter(entries)))
    if key not in entries:
        raise LookupError(f"环境不存在: {name}(可用: {', '.join(entries)})")
    raw = entries[key]
    return {
        "name": key,
        "url": _pick(raw, "url", "baseUrl", "base_url").rstrip("/"),
        "accountId": _pick(raw, "accountId", "account_id"),
        "client_id": _pick(raw, "client_id", "appId", "app_id"),
        "client_secret": _pick(raw, "client_secret", "appSecret", "app_secret"),
        "username": _pick(raw, "username", "loginUser", "login_user", "user"),
        "acgw": _pick(raw, "x-acgw-identity", "acgwIdentity", "acgw_identity"),
        "datacenter": _pick(raw, "datacenter", "dataCenter", "data_center"),
        "normalAccessToken": raw.get("normalAccessToken") is True,
        "_raw": raw,
    }


def _is_default(entry: dict) -> bool:
    v = entry.get("isDefault")
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() == "true"


def save_env(name: str, fields: dict) -> None:
    """写入/更新一个环境(与灵基环境管理同源;双写两种字段名风格)。"""
    cfg = load()
    env = cfg.setdefault("env", {})
    if not isinstance(env, dict):
        raise ValueError("~/.kd/config.json 的 env 段不是对象,拒绝覆盖;请手工检查")
    if fields.pop("isDefault", False):
        for v in env.values():
            if isinstance(v, dict):
                v.pop("isDefault", None)
                v.pop("default", None)
    entry = dict(env.get(name, {}))
    mapping = {
        "url": ("url", "baseUrl"),
        "accountId": ("accountId",),
        "client_id": ("client_id", "appId"),
        "client_secret": ("client_secret", "appSecret"),
        "username": ("username", "loginUser"),
        "acgw": ("x-acgw-identity",),
        "datacenter": ("datacenter",),
    }
    for src, targets in mapping.items():
        val = fields.pop(src, _MISSING)
        if val is _MISSING:
            continue
        for t in targets:
            entry[t] = val
    entry.update(fields)  # 其余字段(如 normalAccessToken)原样落
    entry["name"] = name
    env[name] = entry
    cfg.setdefault("language", "zh_CN")
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
