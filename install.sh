#!/usr/bin/env bash
# install.sh — lingya(ly CLI + ly skill)一键安装(Linux/macOS/WSL)
# 用法: bash install.sh [--root DIR] [--no-path] [--no-skills] [--no-verify]
#                    [--harness workbuddy,zcode,opencode,pi,agents]
# 效果: ly CLI 装到 ~/.lingya(bin 加入 shell rc),SKILL.md 装到各 AI harness 的
#       skills 目录(默认全部五个),并做冒烟验证(--no-verify 跳过)
set -e
ROOT="${HOME}/.lingya"
NO_PATH=0; NO_SKILLS=0; NO_VERIFY=0; HARNESS="all"
while [ $# -gt 0 ]; do
  case "$1" in
    --root) ROOT="$2"; shift 2;;
    --no-path) NO_PATH=1; shift;;
    --no-skills) NO_SKILLS=1; shift;;
    --no-verify) NO_VERIFY=1; shift;;
    --harness) HARNESS="$2"; shift 2;;
    *) echo "未知参数: $1"; exit 2;;
  esac
done
REPO="$(cd "$(dirname "$0")" && pwd)"
command -v python3 >/dev/null 2>&1 || { echo "需要 python3 (3.10+)"; exit 1; }
PYVER="$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
echo "[install] python3: $(command -v python3) ($PYVER)"
case "$PYVER" in
  3.1[0-9]|3.[2-9][0-9]*) ;; # 3.10+
  *) echo "[install] 警告: ly 要求 Python>=3.10,当前 $PYVER,可能无法运行";;
esac
echo "[install] 安装到 $ROOT"

mkdir -p "$ROOT/lib" "$ROOT/bin"
rm -rf "$ROOT/lib/ly"
cp -r "$REPO/src/ly" "$ROOT/lib/ly"

# 启动器:python 入口(跨平台同一份)+ bash 包装
cat > "$ROOT/bin/ly.py" <<'PYEOF'
#!/usr/bin/env python3
"""ly CLI 启动器(安装脚本生成;库体在 ../lib/ly)。"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "lib"))

from ly.cli import main  # noqa: E402

main()
PYEOF
cat > "$ROOT/bin/ly" <<SHEOF
#!/usr/bin/env bash
# cd 到脚本目录再用相对路径调 python:规避 MSYS/GitBash 下 POSIX 绝对路径
# 传给原生 Windows python 时被改写的问题;Linux/macOS/WSL 行为不变
DIR="\$(cd "\$(dirname "\$0")" && pwd)"
cd "\$DIR" && exec python3 ./ly.py "\$@"
SHEOF
chmod +x "$ROOT/bin/ly" "$ROOT/bin/ly.py"

# PATH(bin 加入 shell rc,幂等)
if [ "$NO_PATH" -eq 0 ]; then
  case ":$PATH:" in
    *":$ROOT/bin:"*) echo "[install] PATH 已包含 $ROOT/bin(跳过)";;
    *)
      for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
        [ -f "$rc" ] || continue
        if ! grep -q "\.lingya" "$rc" 2>/dev/null; then
          printf '\nexport PATH="$PATH:%s/bin"\n' "$ROOT" >> "$rc"
          echo "[install] 已写入 $rc(新终端生效)"
        fi
      done
      ;;
  esac
fi

# 技能:实体只装一份,放在通用兼容目录 ~/.agents/skills/ly(agentskills.io 标准,
# Codex/Claude Code/opencode 原生读取);WorkBuddy/ZCode/pi 的目录用符号链接挂到
# 同一份——升级一处、全家生效。链接失败(权限受限/MSYS 降级)自动回退为拷贝。
SKILL_SRC="$REPO/skills/ly"
CANON="$HOME/.agents/skills/ly"
install_canonical() {
  rm -rf "$CANON"
  mkdir -p "$CANON"
  cp -r "$SKILL_SRC/." "$CANON/"
  echo "[install] 技能实体 → $CANON"
}
link_or_copy() {  # $1=harness 名 $2=该 harness 的用户级技能目录
  local dest="$2"
  rm -rf "$dest"
  mkdir -p "$(dirname "$dest")"
  # MSYS/GitBash 的 ln -s 可能静默降级为拷贝:成功且可读才算链接成功
  if ln -s "$CANON" "$dest" 2>/dev/null && [ -e "$dest/SKILL.md" ] && [ -L "$dest" ]; then
    echo "[install] $1 → $dest(链接 → $CANON)"
  else
    rm -rf "$dest"
    mkdir -p "$dest"
    cp -r "$SKILL_SRC/." "$dest/"
    echo "[install] $1 → $dest(拷贝;链接创建失败已回退)"
  fi
}
if [ "$NO_SKILLS" -eq 0 ]; then
  install_canonical
  case "$HARNESS" in
    all) TARGETS="workbuddy zcode opencode pi";;   # agents 即实体本体
    *) TARGETS="$(echo "$HARNESS" | tr ',' ' ' | tr 'A-Z' 'a-z')";;
  esac
  for h in $TARGETS; do
    case "$h" in
      workbuddy) link_or_copy workbuddy "$HOME/.workbuddy/skills/ly";;
      zcode)     link_or_copy zcode     "$HOME/.zcode/skills/ly";;
      opencode)  link_or_copy opencode  "$HOME/.config/opencode/skills/ly";;
      pi)        link_or_copy pi        "$HOME/.pi/agent/skills/ly";;
      agents)    echo "[install] agents 即实体本体($CANON),无需挂载";;
      *) echo "[install] 未知 harness: $h(可选 workbuddy/zcode/opencode/pi/agents/all)";;
    esac
  done
fi

# 冒烟验证(ly doctor 依赖 ERP 环境配置与网络,仅在已配置时提示)
if [ "$NO_VERIFY" -eq 0 ]; then
  echo "[install] 冒烟验证"
  "$ROOT/bin/ly" --version
  if [ -f "$HOME/.kd/config.json" ]; then
    "$ROOT/bin/ly" doctor || echo "[install] doctor 未全绿(检查 ERP 服务是否在线);CLI 本体安装正常"
  else
    echo "[install] 未检测到 ~/.kd/config.json,跳过 doctor;配置环境: ly auth add --name X --url http://host:8080/ierp --account-id <id> --client-id <appId> --client-secret <secret>"
  fi
fi

echo ""
echo "完成!试一试:"
echo "  ly --version                     # 版本"
echo "  ly doctor                        # 环境体检:配置→连通→认证"
echo "  ly auth add --name local --url http://127.0.0.1:8080/ierp --account-id <id> --client-id <appId> --client-secret <secret>"
echo "  ly meta query-forms --params '{\"keyword\":\"BAS\"}'"
echo "  ly data precheck --form <表单编码>   # 业务数据通道四项检查"
echo ""
echo "技能实体在 ~/.agents/skills/ly(通用兼容,Codex/Claude Code/opencode 直接读取),"
echo "WorkBuddy/ZCode/pi 目录已用符号链接挂到同一份——升级重跑本脚本一次即全家生效。"
echo "只想装部分 harness: bash install.sh --harness zcode,pi"
