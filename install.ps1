# install.ps1 — lingya(ly CLI + ly skill)一键安装(Windows)
# 用法: powershell -ExecutionPolicy Bypass -File install.ps1
#   开关: -InstallRoot <dir>  -NoPath  -NoSkills  -NoVerify
# 效果: ly CLI 装到 ~\.lingya(bin 加入用户 PATH),技能装到 ~\.agents\skills\ly,
#       并做冒烟验证(-NoVerify 跳过)
param(
    [string]$InstallRoot = (Join-Path $env:USERPROFILE ".lingya"),
    [switch]$NoPath,
    [switch]$NoSkills,
    [switch]$NoVerify
)
$ErrorActionPreference = "Stop"
$Repo = $PSScriptRoot
$Bin = Join-Path $InstallRoot "bin"
$Lib = Join-Path $InstallRoot "lib"

function Step($msg) { Write-Host "[install] $msg" }

# 1. Python 探测(3.10+)
$pyCmd = $null
if (Get-Command py -ErrorAction SilentlyContinue) { $pyCmd = "py" }
elseif (Get-Command python -ErrorAction SilentlyContinue) { $pyCmd = "python" }
elseif (Get-Command python3 -ErrorAction SilentlyContinue) { $pyCmd = "python3" }
else { Write-Host "[install] 需要 Python 3.10+(未检测到 py/python)" -ForegroundColor Red; exit 1 }
$pyVer = & $pyCmd -c "import sys;print('%d.%d'%sys.version_info[:2])"
Step "python: $pyCmd ($pyVer)"
if ($pyVer -notmatch '^3\.(1[0-9]|[2-9][0-9])') {
    Write-Host "[install] 警告: ly 要求 Python>=3.10,当前 $pyVer,可能无法运行" -ForegroundColor Yellow
}

# 2. 复制库体 + 生成启动器(库体在 lib\ly,启动器只做 sys.path 注入)
Step "安装到 $InstallRoot"
New-Item -ItemType Directory -Force -Path $Lib, $Bin | Out-Null
if (Test-Path (Join-Path $Lib "ly")) { Remove-Item (Join-Path $Lib "ly") -Recurse -Force }
Copy-Item (Join-Path $Repo "src\ly") $Lib -Recurse -Force

$runner = @'
#!/usr/bin/env python3
"""ly CLI 启动器(安装脚本生成;库体在 ../lib/ly)。"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "lib"))

from ly.cli import main  # noqa: E402

main()
'@
Set-Content -Path (Join-Path $Bin "ly.py") -Value $runner -Encoding UTF8
$cmd = @'
@echo off
where py >nul 2>nul && (py -3 "%~dp0ly.py" %*) || (python "%~dp0ly.py" %*)
'@
Set-Content -Path (Join-Path $Bin "ly.cmd") -Value $cmd -Encoding ASCII

# 3. PATH(bin 加入用户环境变量,幂等)
if (-not $NoPath) {
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($userPath -and $userPath.Split(";") -contains $Bin) {
        Step "PATH 已包含 $Bin(跳过)"
    } else {
        Step "加入用户 PATH: $Bin(新开终端生效)"
        $newPath = if ($userPath) { "$userPath;$Bin" } else { $Bin }
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    }
}

# 4. 技能(~\.agents\skills 是 ZCode/Claude Code/Codex/Cursor 通用标准目录;
#    ly 的 SKILL.md 渐进加载引用 references/,须整目录拷贝)
if (-not $NoSkills) {
    $skillDst = Join-Path $env:USERPROFILE ".agents\skills\ly"
    Step "技能 → $skillDst"
    if (Test-Path $skillDst) { Remove-Item $skillDst -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $skillDst | Out-Null
    Copy-Item (Join-Path $Repo "skills\ly\*") $skillDst -Recurse -Force
}

# 5. 冒烟验证(ly doctor 依赖 ERP 环境配置与网络,仅在已配置时执行)
if (-not $NoVerify) {
    Step "冒烟验证"
    & (Join-Path $Bin "ly.cmd") --version
    if ($LASTEXITCODE -ne 0) { Write-Host "[install] ly 启动失败" -ForegroundColor Red; exit 1 }
    if (Test-Path (Join-Path $env:USERPROFILE ".kd\config.json")) {
        & (Join-Path $Bin "ly.cmd") doctor
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[install] doctor 未全绿(检查 ERP 服务是否在线);CLI 本体安装正常" -ForegroundColor Yellow
        }
    } else {
        Step "未检测到 ~\.kd\config.json,跳过 doctor;配置环境: ly auth add --name X --url http://host:8080/ierp --account-id <id> --client-id <appId> --client-secret <secret>"
    }
}

Write-Host ""
Write-Host "完成!试一试:" -ForegroundColor Green
Write-Host '  ly --version'
Write-Host '  ly doctor                        # 环境体检:配置→连通→认证'
Write-Host '  ly auth add --name local --url http://127.0.0.1:8080/ierp --account-id <id> --client-id <appId> --client-secret <secret>'
Write-Host '  ly meta query-forms --params "{\"keyword\":\"BAS\"}"'
Write-Host '  ly data precheck --form <表单编码>   # 业务数据通道四项检查'
Write-Host ""
Write-Host "技能已装到 ~\.agents\skills\ly(含 SKILL.md 与 references\),任何 harness 可直接加载"
