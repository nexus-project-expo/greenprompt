# Demo-day launcher: starts Ollama if needed, builds the UI if missing, starts the server, opens the browser.
# Run from the repo root:  powershell -ExecutionPolicy Bypass -File scripts\start_demo.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

function Test-Ollama {
    try { Invoke-RestMethod http://127.0.0.1:11434/api/tags -TimeoutSec 2 | Out-Null; return $true } catch { return $false }
}

if (-not (Test-Ollama)) {
    Write-Host "Starting Ollama..."
    Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden
    $deadline = (Get-Date).AddMinutes(3)
    while (-not (Test-Ollama) -and (Get-Date) -lt $deadline) { Start-Sleep 3 }
    if (Test-Ollama) { Write-Host "Ollama is up." } else { Write-Host "Ollama did not start; the demo will use the cloud small model." }
} else { Write-Host "Ollama is already running." }

if (-not (Test-Path "web\out\index.html")) {
    Write-Host "Building the UI..."
    Push-Location web; npm install --no-fund --no-audit; npm run build; Pop-Location
}

$busy = Get-Process steam, upc, EpicGamesLauncher -ErrorAction SilentlyContinue
if ($busy) { Write-Host "Close these first for clean GPU readings: $($busy.Name -join ', ')" -ForegroundColor Yellow }

Start-Job { Start-Sleep 4; Start-Process "http://localhost:8000" } | Out-Null
Write-Host "Starting GreenPrompt on http://localhost:8000 (Ctrl+C to stop)"
& "$root\.venv\Scripts\python.exe" -m uvicorn server:app --port 8000 --timeout-graceful-shutdown 2
