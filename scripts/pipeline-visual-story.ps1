# pipeline-visual-story.ps1 — Portfolio E2E: lookBOOK export → cineforge ingest validation
# Usage:
#   pwsh D:\projects\scripts\pipeline-visual-story.ps1
#   pwsh D:\projects\scripts\pipeline-visual-story.ps1 -Push
#   pwsh D:\projects\scripts\pipeline-visual-story.ps1 -Push -CineforgeUrl http://127.0.0.1:8000

param(
    [switch]$Push,
    [string]$CineforgeUrl = "http://127.0.0.1:8765",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$root = "D:\projects"
$lookbook = Join-Path $root "lookBOOK"
$cineforge = Join-Path $root "cineforge"
$fixture = Join-Path $root "scripts\fixtures\visual-story-shot-graph.json"
$lastRunPath = Join-Path $root "scripts\.pipeline-visual-story-last-run.json"
$workRoot = Join-Path $env:TEMP "pipeline-visual-story"
$projectDir = Join-Path $workRoot "demo-bridge"
$startedAt = (Get-Date).ToUniversalTime().ToString("o")

$report = [ordered]@{
    ok           = $false
    started_at   = $startedAt
    finished_at  = $null
    steps        = @()
    export_path  = $null
    shot_count   = 0
    pushed       = $false
    push_response = $null
    error        = $null
}

function Add-Step([string]$Name, [bool]$Pass, [string]$Detail = "") {
    $report.steps += [ordered]@{ name = $Name; pass = $Pass; detail = $Detail }
    $icon = if ($Pass) { "PASS" } else { "FAIL" }
    $color = if ($Pass) { "Green" } else { "Red" }
    Write-Host "[$icon] $Name" -ForegroundColor $color
    if ($Detail) { Write-Host "      $Detail" -ForegroundColor DarkGray }
    if (-not $Pass) { throw "Step failed: $Name — $Detail" }
}

function Write-LastRun {
    $report.finished_at = (Get-Date).ToUniversalTime().ToString("o")
    $report | ConvertTo-Json -Depth 6 | Set-Content -Path $lastRunPath -Encoding utf8
}

try {
    Write-Host "`n=== Visual Story Pipeline E2E ===" -ForegroundColor Cyan
    Write-Host "lookBOOK -> cineforge (M6 bridge)`n"

    Add-Step "fixture present" (Test-Path $fixture) $fixture
    Add-Step "lookBOOK repo" (Test-Path (Join-Path $lookbook "lookbook\pipeline\cineforge_export.py")) $lookbook
    Add-Step "cineforge ingest module" (Test-Path (Join-Path $cineforge "backend\ingest\lookbook.py")) $cineforge

    if (Test-Path $workRoot) { Remove-Item -Recurse -Force $workRoot }
    New-Item -ItemType Directory -Path (Join-Path $projectDir "analysis") -Force | Out-Null

    Copy-Item $fixture (Join-Path $projectDir "analysis\shot_graph.json")
    Add-Step "temp project seeded" (Test-Path (Join-Path $projectDir "analysis\shot_graph.json")) $projectDir

    Push-Location $lookbook
    try {
        $exportPy = @"
import json, sys
from pathlib import Path
from lookbook.pipeline.cineforge_export import export_cineforge_file, CINEFORGE_EXPORT_SCHEMA

project = Path(r'$projectDir')
result = export_cineforge_file(project)
out = result['output_path']
wrapper = json.loads(out.read_text(encoding='utf-8'))
assert wrapper.get('schema') == CINEFORGE_EXPORT_SCHEMA
assert len(wrapper.get('shot_graph', {}).get('shots', [])) >= 1
print(json.dumps({'output_path': str(out), 'shot_count': result['shot_count']}))
"@
        $exportOut = python -c $exportPy 2>&1
        if ($LASTEXITCODE -ne 0) { Add-Step "lookBOOK export" $false ($exportOut -join "`n") }
        $exportJson = $exportOut | ConvertFrom-Json
        $report.export_path = $exportJson.output_path
        $report.shot_count = [int]$exportJson.shot_count
        Add-Step "lookBOOK export-cineforge" $true "$($report.export_path) ($($report.shot_count) shots)"

        $ingest = Get-Content $report.export_path -Raw | ConvertFrom-Json
        Add-Step "ingest schema" ($ingest.schema -eq "lookbook.cineforge_export.v1") $ingest.schema
        Add-Step "shot graph schema" ($ingest.shot_graph.schema -eq "lookbook.shot_graph.v0.3") $ingest.shot_graph.schema
    }
    finally {
        Pop-Location
    }

    if (-not $SkipTests) {
        Push-Location $lookbook
        try {
            pytest --basetemp=D:\tmp\pytest -q tests/test_cineforge_export.py 2>&1 | Out-Host
            Add-Step "lookBOOK pytest (cineforge export)" ($LASTEXITCODE -eq 0)
        }
        finally { Pop-Location }

        Push-Location $cineforge
        try {
            pytest --basetemp=D:\tmp\pytest -q tests/unit/test_lookbook_ingest.py tests/unit/test_lookbook_ingest_choreography.py 2>&1 | Out-Host
            Add-Step "cineforge pytest (lookbook ingest)" ($LASTEXITCODE -eq 0)
        }
        finally { Pop-Location }
    }
    else {
        Add-Step "unit tests" $true "skipped (-SkipTests)"
    }

    if ($Push) {
        try {
            $health = Invoke-RestMethod -Uri "$CineforgeUrl/health" -Method Get -TimeoutSec 5
            Add-Step "cineforge health" ($health.status -eq "ok") $CineforgeUrl
        }
        catch {
            Add-Step "cineforge health" $false "Not reachable at $CineforgeUrl — start backend first"
        }

        $createBody = @{ name = "pipeline-visual-story-e2e" } | ConvertTo-Json
        $created = Invoke-RestMethod -Uri "$CineforgeUrl/projects" -Method Post -Body $createBody -ContentType "application/json" -TimeoutSec 30
        $projectId = $created.id
        Add-Step "cineforge project created" ([bool]$projectId) $projectId

        $ingestBody = Get-Content $report.export_path -Raw | ConvertFrom-Json
        $payload = @{
            shot_graph             = $ingestBody.shot_graph
            replace_existing_shots = $ingestBody.replace_existing_shots
        }
        if ($ingestBody.PSObject.Properties.Name -contains "choreography") {
            $payload.choreography = $ingestBody.choreography
        }
        if ($ingestBody.PSObject.Properties.Name -contains "panels") {
            $payload.panels = $ingestBody.panels
        }

        $pushJson = $payload | ConvertTo-Json -Depth 20 -Compress
        $ingestResp = Invoke-RestMethod -Uri "$CineforgeUrl/projects/$projectId/ingest/lookbook" -Method Post -Body $pushJson -ContentType "application/json" -TimeoutSec 60
        $report.pushed = $true
        $report.push_response = $ingestResp
        $shotCount = if ($ingestResp.shot_count) { $ingestResp.shot_count } else { "?" }
        Add-Step "cineforge ingest push" $true "shot_count=$shotCount project=$projectId"
    }
    else {
        Add-Step "live push" $true "skipped (pass -Push to test running cineforge)"
    }

    $report.ok = $true
    Write-LastRun
    Write-Host "`nVisual story pipeline E2E: OK" -ForegroundColor Green
    exit 0
}
catch {
    $report.ok = $false
    $report.error = $_.Exception.Message
    Write-LastRun
    Write-Host "`nVisual story pipeline E2E: FAILED" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}