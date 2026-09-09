"""ly 自有设置(~/.ly/config.json):write-mode 等。

与 ~/.kd/config.json(环境配置,与灵基同源)分离,互不污染。
"""

from __future__ import annotations

import json
from pathlib import Path

SETTINGS_DIR = Path.home() / ".ly"
WRITE_MODES = ("confirm", "free")


def settings_path() -> Path:
    return SETTINGS_DIR / "config.json"


def load() -> dict:
    p = settings_path()
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def get_write_mode() -> str:
    mode = load().get("write_mode", "confirm")
    return mode if mode in WRITE_MODES else "confirm"


def set_write_mode(mode: str) -> None:
    if mode not in WRITE_MODES:
        raise ValueError(f"write-mode 只能是 {'/'.join(WRITE_MODES)}")
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    data = load()
    data["write_mode"] = mode
    tmp = settings_path().with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(settings_path())
