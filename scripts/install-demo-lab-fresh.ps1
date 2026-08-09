# Fresh-machine Demo Lab install — pip [lab], Tesseract check, preflight, health v5.
# Usage: pwsh D:\projects\lookBOOK\scripts\install-demo-lab-fresh.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "lookBOOK Demo Lab — fresh install" -ForegroundColor Cyan
Write-Host "  Repo: $Root`n"

Write-Host "[1/4] pip install -e `".[lab]`"" -ForegroundColor Yellow
python -m pip install -e ".[lab]"
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

Write-Host "[2/4] Tesseract on PATH" -ForegroundColor Yellow
$tess = Get-Command tesseract -ErrorAction SilentlyContinue
if ($tess) {
    Write-Host "  OK: $($tess.Source)" -ForegroundColor Green
} else {
    Write-Host "  MISSING — install Tesseract:" -ForegroundColor Yellow
    Write-Host "    choco install tesseract   # Windows" -ForegroundColor White
    Write-Host "    brew install tesseract    # macOS" -ForegroundColor White
}

Write-Host "[3/4] preflight" -ForegroundColor Yellow
& "$Root\scripts\preflight-demo-lab.ps1"
$preflightCode = $LASTEXITCODE
if ($preflightCode -eq 1) { throw "preflight failed — lookbook not importable" }

Write-Host "[4/4] health probe (ephemeral server)" -ForegroundColor Yellow
$healthPy = @"
import json, threading, time, urllib.request
from http.server import HTTPServer
from lookbook.lab_server import LabHandler

server = HTTPServer(('127.0.0.1', 0), LabHandler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
host, port = server.server_address
time.sleep(0.3)
with urllib.request.urlopen(f'http://{host}:{port}/health', timeout=5) as resp:
    body = json.loads(resp.read().decode())
server.shutdown()
assert body.get('ok') and body.get('version', 0) >= 5, body
print(json.dumps({'version': body['version'], 'ready': body['capabilities']['ready_for_pipeline']}))
"@
$healthOut = python -c $healthPy 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host $healthOut -ForegroundColor Red
    throw "health probe failed"
}
$health = $healthOut | ConvertFrom-Json
Write-Host "  Lab ready v$($health.version) · ready_for_pipeline=$($health.ready)" -ForegroundColor Green

if ($preflightCode -eq 2) {
    Write-Host "`nInstall complete with warnings — pipeline may use fallbacks until Tesseract is installed." -ForegroundColor Yellow
    exit 2
}

Write-Host "`nFresh install OK — run: pwsh scripts/start-demo-lab.ps1" -ForegroundColor Green
exit 0