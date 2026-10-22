<#
  一键安装：检查依赖 → 创建 Python 虚拟环境 → 安装后端依赖 → 安装前端依赖 → 构建前端
  用法： powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
#>

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Write-Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "  ✓ $msg" -ForegroundColor Green }
function Write-Warn2($msg){ Write-Host "  ! $msg" -ForegroundColor Yellow }

# ---------- 1. Python ----------
Write-Step "检查 Python"
$python = $null
foreach ($cand in @("python", "py -3.12", "py -3.11", "py -3")) {
    if ($cand -eq "python") {
        if (Get-Command python -ErrorAction SilentlyContinue) { $python = "python"; break }
    } else {
        $parts = $cand.Split(" ")
        if (Get-Command $parts[0] -ErrorAction SilentlyContinue) { $python = $cand; break }
    }
}
if (-not $python) {
    Write-Host "  未找到 Python 3.11+，请先安装： https://www.python.org/downloads/" -ForegroundColor Red
    exit 1
}
Write-Ok "Python: $python (& $python --version)"

# ---------- 2. FFmpeg ----------
Write-Step "检查 FFmpeg"
$ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
$ffprobe = Get-Command ffprobe -ErrorAction SilentlyContinue
if ($ffmpeg -and $ffprobe) {
    Write-Ok "FFmpeg: $($ffmpeg.Source)"
} else {
    Write-Warn2 "未找到 ffmpeg / ffprobe"
    Write-Host "     winget install --id BtbN.FFmpeg.GPL.8.1 --exact" -ForegroundColor Yellow
    Write-Host "     或手动下载 https://www.gyan.dev/ffmpeg/builds/ 并加入 PATH" -ForegroundColor Yellow
    Write-Host "     也可在 services/api/.env 中设置 VC_FFMPEG / VC_FFPROBE 的绝对路径" -ForegroundColor Yellow
}

# ---------- 3. Python 虚拟环境 ----------
Write-Step "准备 Python 虚拟环境"
$Venv = Join-Path $Root "services\api\.venv"
if (-not (Test-Path $Venv)) {
    & $python -m venv $Venv
    Write-Ok "已创建 $Venv"
} else {
    Write-Ok "已存在，跳过创建"
}
$VenvPy = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $VenvPy)) {
    Write-Host "  虚拟环境损坏，请删除 $Venv 后重试" -ForegroundColor Red
    exit 1
}

# ---------- 4. 后端依赖（含 monorepo 内部包）----------
Write-Step "安装后端依赖"
& $VenvPy -m pip install --upgrade pip --quiet
& $VenvPy -m pip install -r (Join-Path $Root "services\api\requirements.txt") --quiet
Write-Ok "后端依赖安装完成（含 packages/media-core、packages/ai-providers）"

# ---------- 5. 前端 ----------
Write-Step "准备前端"
$npm = $null
if (Get-Command npm.cmd -ErrorAction SilentlyContinue)      { $npm = "npm.cmd" }
elseif (Get-Command npm -ErrorAction SilentlyContinue)       { $npm = "npm" }
elseif (Test-Path "C:\Program Files\nodejs\npm.cmd")        { $npm = "C:\Program Files\nodejs\npm.cmd" }

if (-not $npm) {
    Write-Warn2 "未找到 npm，跳过前端构建（后端接口仍可使用）"
} else {
    Push-Location (Join-Path $Root "apps\web")
    & $npm install --no-audit --no-fund
    & $npm run build
    Pop-Location
    Write-Ok "前端构建完成 -> apps/web/dist"
}

# ---------- 6. 环境变量样例 ----------
$EnvFile = Join-Path $Root "services\api\.env"
if (-not (Test-Path $EnvFile)) {
    Copy-Item (Join-Path $Root "services\api\.env.example") $EnvFile
    Write-Ok "已生成 services/api/.env（可按需修改）"
}

Write-Host "`n安装完成。启动服务：" -ForegroundColor Green
Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\start.ps1" -ForegroundColor Green
