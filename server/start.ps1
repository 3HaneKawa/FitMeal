param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$port = 8765
$healthUrl = "http://127.0.0.1:$port/health"
$appUrl = "http://127.0.0.1:$port/app/?v=0.5.1"
$chatStatusUrl = "http://127.0.0.1:$port/chat/status"
$embedRoot = Join-Path (Split-Path -Parent $root) "embed-server"
$embedHealthUrl = "http://127.0.0.1:8766/health"
$browserJob = $null

function Get-DotEnvValue {
    param([string]$Path, [string]$Key)
    if (-not (Test-Path -LiteralPath $Path)) { return "" }
    foreach ($rawLine in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) { continue }
        $parts = $line.Split("=", 2)
        if ($parts[0].Trim() -eq $Key) { return $parts[1].Trim().Trim('"').Trim("'") }
    }
    return ""
}

function Test-HttpOk {
    param([string]$Url, [int]$TimeoutSec = 3)
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    } catch { return $false }
}

function Wait-HttpOk {
    param([string]$Url, [int]$Attempts = 60, [int]$DelaySeconds = 1)
    for ($i = 0; $i -lt $Attempts; $i++) {
        if (Test-HttpOk -Url $Url -TimeoutSec 2) { return $true }
        Start-Sleep -Seconds $DelaySeconds
    }
    return $false
}

function Get-DifyProbeUrl {
    param([string]$ChatEndpoint)
    if ($ChatEndpoint) {
        try {
            $uri = [System.Uri]$ChatEndpoint
            if ($uri.Scheme -and $uri.Authority) {
                return "$($uri.Scheme)://$($uri.Authority)/console/api/setup"
            }
        } catch {}
    }
    return "http://127.0.0.1/console/api/setup"
}

Push-Location $root
try {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Host ""
        Write-Host "[FitMeal] uv was not found." -ForegroundColor Red
        Write-Host "Install uv first, then run this launcher again." -ForegroundColor Yellow
        exit 1
    }

    $envPath = Join-Path $root ".env"
    if (-not (Test-Path -LiteralPath $envPath)) {
        Write-Host "[FitMeal] 缺少 .env，无法调用 Dify。" -ForegroundColor Red
        Write-Host "请先执行 Copy-Item .env.example .env，并填写 DIFY_API_KEY。" -ForegroundColor Yellow
        exit 1
    }
    if ([string]::IsNullOrWhiteSpace((Get-DotEnvValue -Path $envPath -Key "DIFY_API_KEY"))) {
        Write-Host "[FitMeal] .env 中没有 DIFY_API_KEY。" -ForegroundColor Red
        Write-Host "请填入 Dify 应用 Token，且不要提交到 Git。" -ForegroundColor Yellow
        exit 1
    }
    $difyChatUrl = Get-DotEnvValue -Path $envPath -Key "DIFY_API_URL"
    if ([string]::IsNullOrWhiteSpace($difyChatUrl)) { $difyChatUrl = "http://127.0.0.1/v1/chat-messages" }
    $difyProbeUrl = Get-DifyProbeUrl -ChatEndpoint $difyChatUrl
    if (-not (Test-HttpOk -Url $difyProbeUrl -TimeoutSec 3)) {
        Write-Host "[FitMeal] 无法连接 Dify：$difyProbeUrl" -ForegroundColor Red
        Write-Host "请确认 Docker Desktop 和 Dify 容器已经启动。" -ForegroundColor Yellow
        exit 1
    }
    if (-not (Test-HttpOk -Url $embedHealthUrl -TimeoutSec 2)) {
        Write-Host "[FitMeal] 8766 向量服务没有运行。" -ForegroundColor Red
        Write-Host "请先在 D:\Desktop\ai\embed-server 启动本地向量服务。" -ForegroundColor Yellow
        exit 1
    }

    try {
        $existing = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 1
        if ($existing.status -eq "ok") {
            Write-Host "[FitMeal] Service is already running: $appUrl" -ForegroundColor Green
            if (-not $NoBrowser) {
                Start-Process $appUrl
            }
            exit 0
        }
    }
    catch {
        # No healthy FitMeal service is listening yet.
    }

    $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($listener) {
        Write-Host ""
        Write-Host "[FitMeal] Port $port is already used by another process." -ForegroundColor Red
        Write-Host "Close that process or change the port in server/start.ps1." -ForegroundColor Yellow
        exit 1
    }

    if (-not $NoBrowser) {
        $browserJob = Start-Job -ScriptBlock {
            param($healthAddress, $statusAddress, $pageAddress)
            for ($i = 0; $i -lt 60; $i++) {
                try {
                    $health = Invoke-RestMethod -Uri $healthAddress -TimeoutSec 1
                    $chatStatus = Invoke-RestMethod -Uri $statusAddress -TimeoutSec 1
                    if ($health.status -eq "ok" -and $chatStatus.configured) {
                        Start-Process $pageAddress
                        return
                    }
                }
                catch {
                    Start-Sleep -Seconds 1
                }
            }
        } -ArgumentList $healthUrl, $chatStatusUrl, $appUrl
    }

    Write-Host ""
    Write-Host "FitMeal - Dify 端到端演示" -ForegroundColor Cyan
    Write-Host "Frontend:  $appUrl"
    Write-Host "Health:    $healthUrl"
    Write-Host "Dify API:  $difyChatUrl"
    Write-Host "Embedding: $embedHealthUrl"
    Write-Host "Press Ctrl+C to stop the FitMeal service."
    Write-Host ""

    & uv run --python 3.12 --with fastapi --with uvicorn `
        uvicorn app:app --app-dir server --host 127.0.0.1 --port 8765

    if ($LASTEXITCODE -ne 0) {
        throw "FitMeal service exited with code $LASTEXITCODE."
    }
}
finally {
    if ($browserJob) {
        Stop-Job -Job $browserJob -ErrorAction SilentlyContinue
        Remove-Job -Job $browserJob -Force -ErrorAction SilentlyContinue
    }
    Pop-Location
}

