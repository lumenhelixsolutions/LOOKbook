# Start lookBOOK director-graph LangGraph sidecar on port 7791.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$port = if ($env:DIRECTOR_GRAPH_PORT) { $env:DIRECTOR_GRAPH_PORT } else { "7791" }

Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match '^python' -and $_.CommandLine -match 'director-graph[\\/]server\.py' } |
    ForEach-Object {
        Write-Host "Stopping stale director-graph (PID $($_.ProcessId))" -ForegroundColor DarkYellow
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

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
Write-Host "lookBOOK director-graph sidecar" -ForegroundColor Cyan
Write-Host "  http://127.0.0.1:$port/health" -ForegroundColor Green
python director-graph/server.py