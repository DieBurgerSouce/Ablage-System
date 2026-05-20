# Migration Script: docs/ultraplan/ -> Obsidian Vault 02_System_Reality/
# Created: 2026-05-04 by Claude (continuation of Vault setup)
# Purpose: Migrate Ultraplan output (28 files) into the Vault as Single Source of Truth

$ErrorActionPreference = "Stop"

$src = "C:\Users\benfi\Ablage_System\docs\ultraplan"
$dst = "C:\Users\benfi\Obsidian\Storage\_Ablage_System\02_System_Reality"
$today = Get-Date -Format "yyyy-MM-dd"

# UTF-8 without BOM (Obsidian-friendly)
$utf8NoBom = New-Object System.Text.UTF8Encoding $false

function Write-FileNoBom {
    param([string]$Path, [string]$Content)
    $dir = Split-Path -Parent $Path
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    [System.IO.File]::WriteAllText($Path, $Content, $utf8NoBom)
}

function Get-Frontmatter {
    param(
        [string]$SourcePath,
        [string[]]$Tags
    )
    $tagBlock = ($Tags | ForEach-Object { "  - $_" }) -join "`n"
    return @"
---
tags:
$tagBlock
created: 2026-05-03
last_updated: $today
source: $SourcePath
---

"@
}

# ============================================================
# Phase A — 5 Stand-alone Top-Level Dokumente
# ============================================================
Write-Host "=== Phase A: Top-Level Dokumente ===" -ForegroundColor Cyan

$topLevel = @(
    @{ src = "00_GROUND_TRUTH.md";          dst = "GROUND_TRUTH.md";          tags = @("ablage-system", "system-reality", "ultraplan", "ground-truth") }
    @{ src = "CROSS_CUTTING_FINDINGS.md";   dst = "CROSS_CUTTING_FINDINGS.md"; tags = @("ablage-system", "system-reality", "ultraplan", "findings") }
    @{ src = "GAP_ANALYSIS.md";             dst = "GAP_ANALYSIS.md";          tags = @("ablage-system", "system-reality", "ultraplan", "gaps", "tier-analysis") }
    @{ src = "EXECUTIVE_DASHBOARD.md";      dst = "EXECUTIVE_DASHBOARD.md";   tags = @("ablage-system", "system-reality", "ultraplan", "dashboard", "status") }
    @{ src = "ULTRAPLAN_MASTER.md";         dst = "ULTRAPLAN_MASTER.md";      tags = @("ablage-system", "system-reality", "ultraplan", "master") }
)

foreach ($f in $topLevel) {
    $srcPath = Join-Path $src $f.src
    $dstPath = Join-Path $dst $f.dst
    $body = Get-Content -Raw -Encoding UTF8 -Path $srcPath
    $fm = Get-Frontmatter -SourcePath "docs/ultraplan/$($f.src)" -Tags $f.tags
    Write-FileNoBom -Path $dstPath -Content "$fm$body"
    Write-Host "  -> $($f.dst)" -ForegroundColor Green
}

# ============================================================
# Phase B — 11 Perspektiven
# ============================================================
Write-Host "=== Phase B: Perspektiven (11 Files) ===" -ForegroundColor Cyan

$perspDst = Join-Path $dst "perspectives"
if (-not (Test-Path $perspDst)) {
    New-Item -ItemType Directory -Path $perspDst -Force | Out-Null
}

Get-ChildItem -Path (Join-Path $src "perspectives\*.md") | ForEach-Object {
    $name = $_.Name
    $body = Get-Content -Raw -Encoding UTF8 -Path $_.FullName
    $fm = Get-Frontmatter -SourcePath "docs/ultraplan/perspectives/$name" -Tags @("ablage-system", "system-reality", "ultraplan", "perspective")
    Write-FileNoBom -Path (Join-Path $perspDst $name) -Content "$fm$body"
    Write-Host "  -> perspectives/$name" -ForegroundColor Green
}

# ============================================================
# Phase C — 10 Tiefen-Audits
# ============================================================
Write-Host "=== Phase C: Tiefen-Audits (10 Files) ===" -ForegroundColor Cyan

$auditDst = Join-Path $dst "audit"
if (-not (Test-Path $auditDst)) {
    New-Item -ItemType Directory -Path $auditDst -Force | Out-Null
}

Get-ChildItem -Path (Join-Path $src "audit\*.md") | ForEach-Object {
    $name = $_.Name
    $body = Get-Content -Raw -Encoding UTF8 -Path $_.FullName
    $fm = Get-Frontmatter -SourcePath "docs/ultraplan/audit/$name" -Tags @("ablage-system", "system-reality", "ultraplan", "audit")
    Write-FileNoBom -Path (Join-Path $auditDst $name) -Content "$fm$body"
    Write-Host "  -> audit/$name" -ForegroundColor Green
}

# ============================================================
# Phase D — Execution Plan (operatives Cookbook, separate Datei)
# ============================================================
Write-Host "=== Phase D: Execution Plan ===" -ForegroundColor Cyan

$execSrc = Join-Path $src "EXECUTION_PLAN.md"
$execDst = Join-Path $dst "EXECUTION_PLAN.md"
$body = Get-Content -Raw -Encoding UTF8 -Path $execSrc
$fm = Get-Frontmatter -SourcePath "docs/ultraplan/EXECUTION_PLAN.md" -Tags @("ablage-system", "system-reality", "ultraplan", "execution", "cookbook")
Write-FileNoBom -Path $execDst -Content "$fm$body"
Write-Host "  -> EXECUTION_PLAN.md" -ForegroundColor Green

# ============================================================
# Verifikation
# ============================================================
Write-Host "=== Verifikation ===" -ForegroundColor Yellow
$migrated = (Get-ChildItem -Path $dst -Recurse -File -Filter "*.md" | Measure-Object).Count
Write-Host "Total markdown files in 02_System_Reality\: $migrated"

# Listing
Get-ChildItem -Path $dst -Recurse -File -Filter "*.md" | Sort-Object FullName | ForEach-Object {
    $relPath = $_.FullName.Replace($dst, "").TrimStart("\")
    Write-Host "  $relPath" -ForegroundColor Gray
}

Write-Host ""
Write-Host "Migration complete." -ForegroundColor Green
