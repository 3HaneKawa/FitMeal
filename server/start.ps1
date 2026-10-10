param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$port = 8765
$healthUrl = "http://127.0.0.1:$port/health"
$appUrl = "http://127.0.0.1:$port/app/?v=0.4.2"
$browserJob = $null

Push-Location $root
try {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Host ""
        Write-Host "[FitMeal] uv was not found." -ForegroundColor Red
        Write-Host "Install uv first, then run this launcher again." -ForegroundColor Yellow
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
            param($healthAddress, $pageAddress)
            for ($i = 0; $i -lt 60; $i++) {
                try {
                    $health = Invoke-RestMethod -Uri $healthAddress -TimeoutSec 1
                    if ($health.status -eq "ok") {
                        Start-Process $pageAddress
                        return
                    }
                }
                catch {
                    Start-Sleep -Seconds 1
                }
            }
        } -ArgumentList $healthUrl, $appUrl
    }

    Write-Host ""
    Write-Host "FitMeal local demo" -ForegroundColor Cyan
    Write-Host "Frontend: $appUrl"
    Write-Host "Health:   $healthUrl"
    Write-Host "Press Ctrl+C to stop the service."
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

