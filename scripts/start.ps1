<#
  启动服务：默认监听 0.0.0.0:8080，前端由后端一并托管
  用法： powershell -ExecutionPolicy Bypass -File scripts\start.ps1 [-Port 8080] [-Reload] [-Dev]
#>

param(
    [int]$Port = 8080,
    [switch]$Reload,
    [switch]$Dev
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$VenvPy = Join-Path $Root "services\api\.venv\Scripts\python.exe"
if (-not (Test-Path $VenvPy)) {
    Write-Host "未找到虚拟环境，请先运行 scripts\setup.ps1" -ForegroundColor Red
    exit 1
}

# 载入 services/api/.env（如果存在）
$EnvFile = Join-Path $Root "services\api\.env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $idx = $line.IndexOf("=")
            $k = $line.Substring(0, $idx).Trim()
            $v = $line.Substring($idx + 1).Trim()
            if ($v -and $v -notmatch "^\s*$") {
                [Environment]::SetEnvironmentVariable($k, $v, "Process")
            }
        }
    }
    Write-Host "已载入 services/api/.env" -ForegroundColor DarkGray
}

# 确保 FFmpeg 在 PATH 中（若配置了绝对路径则无需）
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    $ff = [Environment]::GetEnvironmentVariable("VC_FFMPEG", "Process")
    if ($ff -and (Test-Path $ff)) {
        $dir = Split-Path -Parent $ff
        $env:Path = "$dir;$env:Path"
        Write-Host "已把 $dir 加入 PATH" -ForegroundColor DarkGray
    }
}

if ($Dev) {
    Write-Host "`n开发模式：后端 :8080 + 前端 :5173（Vite 热更新）`n" -ForegroundColor Cyan
    $job = Start-Job -ScriptBlock {
        Set-Location $args[0]
        & (Join-Path $args[0] "services\api\.venv\Scripts\python.exe") -m uvicorn app.main:app --reload --port 8080 --host 127.0.0.1
    } -ArgumentList (Join-Path $Root "services\api")
    Start-Sleep -Seconds 3
    Push-Location (Join-Path $Root "apps\web")
    npm.cmd run dev
    Pop-Location
    Stop-Job $job -ErrorAction SilentlyContinue
    exit
}

$args = @("-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "$Port")
if ($Reload) { $args += "--reload" }

Write-Host "`n  VideoNarrator AI · AI 视频解说工作站" -ForegroundColor Cyan
Write-Host "  服务地址： http://127.0.0.1:$Port" -ForegroundColor Green
Write-Host "  数据目录： $(Join-Path $Root 'data')`n" -ForegroundColor DarkGray

Push-Location (Join-Path $Root "services\api")
& $VenvPy @args
Pop-Location
