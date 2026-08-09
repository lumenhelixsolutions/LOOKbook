# Start lookBOOK Demo Lab (API + UI on port 8042). Safe to run from any directory.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

& "$Root\scripts\preflight-demo-lab.ps1"
if ($LASTEXITCODE -eq 2) {
    Write-Host "Starting anyway — pipeline may use fallbacks until deps are installed." -ForegroundColor Yellow
}

$port = if ($env:LOOKBOOK_LAB_PORT) { $env:LOOKBOOK_LAB_PORT } else { "8042" }

# Single-server guard: stop any stale lab_server python processes
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match '^python' -and $_.CommandLine -match 'lookbook\.lab_server' } |
    ForEach-Object {
        Write-Host "Stopping stale lab_server (PID $($_.ProcessId))" -ForegroundColor DarkYellow
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

# Free the port if another process is still listening
Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue |
    Where-Object { $_.State -eq 'Listen' } |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object {
        if ($_ -and $_ -ne 0) {
            Write-Host "Freeing port $port (PID $_)" -ForegroundColor DarkYellow
            Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
        }
    }

Start-Sleep -Seconds 1
$stillListening = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($stillListening) {
    Write-Host "WARNING: port $port still in use — lab may fail to bind" -ForegroundColor Red
}

$url = "http://127.0.0.1:$port/"
Write-Host ""
Write-Host "lookBOOK Demo Lab" -ForegroundColor Cyan
Write-Host "  Open: $url" -ForegroundColor Green
Write-Host "  (API + UI — do not use port 8766)" -ForegroundColor DarkGray
Write-Host ""

Start-Process $url
python -m lookbook.lab_server