# 启动 FitMeal 本地数据服务（方案 B）
# 用法：在项目根目录执行  powershell -ExecutionPolicy Bypass -File server\start.ps1
# 停止：在该窗口按 Ctrl+C
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    Write-Host "FitMeal 数据服务启动中： http://127.0.0.1:8765/health"
    uv run --python 3.12 --with fastapi --with uvicorn `
        uvicorn app:app --app-dir server --host 0.0.0.0 --port 8765
}
finally {
    Pop-Location
}
