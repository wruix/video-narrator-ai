<#
  一键自检：依次运行四个测试脚本
  用法： powershell -ExecutionPolicy Bypass -File scripts\test-all.ps1 [-BaseUrl http://127.0.0.1:8080]
#>

param(
    [string]$BaseUrl = "http://127.0.0.1:8080"
)

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
$Py = Join-Path $Root "services\api\.venv\Scripts\python.exe"

if (-not (Test-Path $Py)) {
    Write-Host "未找到虚拟环境，请先运行 scripts\setup.ps1" -ForegroundColor Red
    exit 1
}

$failed = @()

function Run-Test($name, $script, $argsList) {
    Write-Host "`n################ $name ################" -ForegroundColor Cyan
    & $Py (Join-Path $Root "scripts\$script") @argsList
    if ($LASTEXITCODE -ne 0) {
        $script:failed += $name
        Write-Host "$name 失败" -ForegroundColor Red
    } else {
        Write-Host "$name 通过" -ForegroundColor Green
    }
}

Run-Test "媒体链路自检" "selftest.py" @()
Run-Test "模型适配层测试" "test_providers.py" @()
Run-Test "接口集成测试" "api_test.py" @($BaseUrl)
Run-Test "密钥存储检查" "check_key_storage.py" @()

# 桌面端后端定位与拉起（需要 Node.js）
if (Get-Command node -ErrorAction SilentlyContinue) {
    Write-Host "`n################ 桌面端后端自检 ################" -ForegroundColor Cyan
    & node (Join-Path $Root "apps\desktop\dist\backend-check.js")
    if ($LASTEXITCODE -ne 0) {
        $failed += "桌面端后端自检"
        Write-Host "桌面端后端自检 失败" -ForegroundColor Red
    } else {
        Write-Host "桌面端后端自检 通过" -ForegroundColor Green
    }
}

Write-Host ""
if ($failed.Count -eq 0) {
    Write-Host "全部测试通过 ✓" -ForegroundColor Green
    exit 0
} else {
    Write-Host "失败项： $($failed -join ', ')" -ForegroundColor Red
    exit 1
}
