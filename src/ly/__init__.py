"""ly — Lingya 个人跨 harness 金蝶 ERP 开发 CLI。"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("ly-cli")
except PackageNotFoundError:  # 源码直接引用场景的回退,随 pyproject 同步
    __version__ = "0.3.0"
