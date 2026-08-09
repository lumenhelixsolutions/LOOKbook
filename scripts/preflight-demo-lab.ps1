# Demo Lab Gen 2 preflight — verify pipeline dependencies before launch.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "lookBOOK Demo Lab preflight" -ForegroundColor Cyan

$py = @"
from lookbook.lab_capabilities import get_lab_capabilities
import json
print(json.dumps(get_lab_capabilities(), indent=2))
"@

$capJson = python -c $py 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "FAIL: could not load lookbook" -ForegroundColor Red
    Write-Host $capJson
    exit 1
}

$cap = $capJson | ConvertFrom-Json
Write-Host "  panels:    $($cap.panels)" -ForegroundColor $(if ($cap.panels) { 'Green' } else { 'Yellow' })
Write-Host "  OCR:       $($cap.ocr)" -ForegroundColor $(if ($cap.ocr) { 'Green' } else { 'Yellow' })
Write-Host "  vision:    $($cap.vision_llm)" -ForegroundColor $(if ($cap.vision_llm) { 'Green' } else { 'DarkGray' })
Write-Host "  ready:     $($cap.ready_for_pipeline)" -ForegroundColor $(if ($cap.ready_for_pipeline) { 'Green' } else { 'Red' })

if (-not $cap.ready_for_pipeline) {
    Write-Host ""
    Write-Host "Install lab dependencies:" -ForegroundColor Yellow
    Write-Host "  pip install -e `".[lab]`"" -ForegroundColor White
    Write-Host "  choco install tesseract   # or OS package manager" -ForegroundColor White
    foreach ($n in $cap.notes) { Write-Host "  - $n" -ForegroundColor DarkGray }
    exit 2
}

Write-Host "Preflight OK" -ForegroundColor Green
exit 0