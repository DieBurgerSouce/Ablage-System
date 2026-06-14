# =============================================================================
# A-Z-Simulations-Loop: Orchestriert den kompletten Test-Durchlauf der App
# gegen den Docker-Stack (Test-Overrides + CPU-OCR).
#
# Verwendung (PowerShell 7+, Repo-Root):
#   .\scripts\sim_a_to_z.ps1                       # alle Stufen
#   .\scripts\sim_a_to_z.ps1 -Stages gates,unit    # Teilmenge
#   .\scripts\sim_a_to_z.ps1 -SkipBuild            # ohne Image-Build
#   .\scripts\sim_a_to_z.ps1 -LoopId 3             # Reportname-Suffix
#
# Stufen (Reihenfolge):
#   build    - Frontend-Image bauen (Code ist ins Nginx-Image gebacken)
#   up       - Stack hochfahren (--wait) + Migration + Reset + Seed
#   gates    - Health-Gates (compose ps, /health, GPU-Healthcheck, Prometheus)
#   docker   - tests/docker (Container/Targets/Log-Scan, Host-seitig)
#   unit     - Backend tests/unit im Container
#   security - Backend tests/security im Container
#   integ    - Backend tests/integration (-m "not gpu") im Container
#   api      - Schemathesis-Fuzz (Git Bash, scripts/run_schemathesis.sh)
#   e2e      - Playwright chromium (frontend/e2e)
#   a11y     - Playwright a11y-Projekt
#   vitest   - Frontend-Unit (seriell, fileParallelism=false)
#   monitor  - Prometheus-Targets up + 0 firing Alerts + Grafana-Health
#
# Exit-Code 0 = alle gewaehlten Stufen gruen. Logs unter $LogDir, Summary als
# Markdown unter docs/qa-reports/.
# NIEMALS gegen eine Instanz mit echten Daten fahren (PII-Regel).
# =============================================================================
[CmdletBinding()]
param(
    [string[]]$Stages = @('build','up','gates','docker','unit','security','integ','api','e2e','a11y','vitest','monitor'),
    [switch]$SkipBuild,
    [int]$LoopId = 0,
    [string]$BackendUrl = 'http://localhost:8000',
    [string]$FrontendUrl = 'http://localhost:80'
)

$ErrorActionPreference = 'Continue'
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

# Bei `pwsh -File` kommt "-Stages a,b,c" als EIN String an -> normalisieren.
$Stages = @($Stages | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })

$ComposeFiles = @('-f','docker-compose.yml','-f','docker-compose.test.yml','-f','docker-compose.cpu-ocr.yml')
$Stamp = Get-Date -Format 'yyyy-MM-dd'
$RunStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$LogDir = Join-Path $RepoRoot ".claude/reviews/$Stamp/loop-logs/run-$RunStamp"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Results = [ordered]@{}

function Invoke-Stage {
    param([string]$Name, [scriptblock]$Body)
    if ($Stages -notcontains $Name) { return }
    $log = Join-Path $LogDir "$Name.log"
    Write-Host "==== Stufe: $Name ====" -ForegroundColor Cyan
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $code = 1
    try {
        & $Body 2>&1 | Tee-Object -FilePath $log | Out-Host
        $code = $LASTEXITCODE
        if ($null -eq $code) { $code = 0 }
    } catch {
        $_ | Out-File -Append -FilePath $log
        $code = 1
    }
    $sw.Stop()
    $Results[$Name] = [pscustomobject]@{ Stage=$Name; ExitCode=$code; Seconds=[int]$sw.Elapsed.TotalSeconds; Log=$log }
    $color = if ($code -eq 0) { 'Green' } else { 'Red' }
    Write-Host ("==== {0}: {1} ({2}s) ====" -f $Name, ($(if ($code -eq 0) {'GRUEN'} else {"ROT ($code)"})), [int]$sw.Elapsed.TotalSeconds) -ForegroundColor $color
}

# --- Stufen ------------------------------------------------------------------

Invoke-Stage 'build' {
    if ($SkipBuild) { Write-Host 'SkipBuild gesetzt - Build uebersprungen'; $global:LASTEXITCODE = 0; return }
    # Docker Desktop wirft unter Last sporadische grpc-/API-Abbrueche -> bis zu 3 Versuche
    foreach ($attempt in 1..3) {
        docker compose @ComposeFiles build frontend
        if ($LASTEXITCODE -eq 0) { return }
        Write-Host "Build-Versuch $attempt fehlgeschlagen (Exit $LASTEXITCODE) - Retry in 15s"
        Start-Sleep 15
    }
}

Invoke-Stage 'up' {
    docker compose @ComposeFiles up -d --wait
    if ($LASTEXITCODE -ne 0) { return }
    docker compose @ComposeFiles exec -T backend alembic upgrade head
    if ($LASTEXITCODE -ne 0) { return }
    docker compose @ComposeFiles exec -T backend alembic current
    if ($LASTEXITCODE -ne 0) { return }
    curl.exe -fsS -X POST "$BackendUrl/api/v1/test/reset-state"
    if ($LASTEXITCODE -ne 0) { Write-Host 'reset-state fehlgeschlagen (TESTING=true? ENVIRONMENT nicht prod?)'; return }
    Get-Content (Join-Path $RepoRoot 'scripts/seed_e2e.py') -Raw |
        docker compose @ComposeFiles exec -T backend python -
}

Invoke-Stage 'gates' {
    $bad = docker compose @ComposeFiles ps --format json |
        ConvertFrom-Json |
        Where-Object { $_.Health -and $_.Health -ne 'healthy' }
    if ($bad) { Write-Host "Unhealthy: $($bad.Name -join ', ')"; $global:LASTEXITCODE = 1; return }
    curl.exe -fsS "$BackendUrl/health" | Out-Null;            if ($LASTEXITCODE -ne 0) { Write-Host 'Backend /health ROT'; return }
    curl.exe -fsS "$FrontendUrl/health" | Out-Null;           if ($LASTEXITCODE -ne 0) { Write-Host 'Frontend /health ROT'; return }
    curl.exe -fsS "$BackendUrl/api/v1/health/gpu" | Out-Null; if ($LASTEXITCODE -ne 0) { Write-Host 'GPU-Healthcheck ROT'; return }
    Write-Host 'Alle Health-Gates gruen.'
}

# --continue-on-collection-errors: tests/unit/orchestration/** importiert das
# Host-Tooling-Paket 'orchestration' (.claude/orchestration, im Container nicht
# gemountet) -> ohne das Flag bricht die GESAMTE Collection ab (exit 2).
# GNU timeout als Haenger-Schutz: ein deadlockender Test (vgl. CircuitBreaker-
# Selbst-Deadlock, W3b) soll die Stufe nach einem harten Limit ROT beenden
# (Exit 124) statt den Loop unendlich zu blockieren. pytest-timeout ist im
# Image nicht installiert (read-only Rootfs).
Invoke-Stage 'docker'   { python -m pytest tests/docker -q --no-header }
Invoke-Stage 'unit'     { docker compose @ComposeFiles exec -T backend timeout -k 30 7200 pytest tests/unit -q --no-header -p no:cacheprovider --continue-on-collection-errors }
Invoke-Stage 'security' { docker compose @ComposeFiles exec -T backend timeout -k 30 3600 pytest tests/security -q --no-header -p no:cacheprovider --continue-on-collection-errors }
Invoke-Stage 'integ'    { docker compose @ComposeFiles exec -T backend timeout -k 30 5400 pytest tests/integration -q --no-header -p no:cacheprovider -m 'not gpu' --continue-on-collection-errors }

Invoke-Stage 'api' {
    $env:BASE_URL = $BackendUrl
    if (-not $env:MAX_EXAMPLES) { $env:MAX_EXAMPLES = '25' }
    if (-not $env:MAX_FAILURES) { $env:MAX_FAILURES = '50' }
    # Git-Bash EXPLIZIT: blankes 'bash' loest auf WSL auf (dort fehlt python/
    # schemathesis); das Skript braucht die Host-Python-Umgebung.
    $gitBash = 'C:\Program Files\Git\bin\bash.exe'
    if (-not (Test-Path $gitBash)) { Write-Host "Git-Bash fehlt: $gitBash"; $global:LASTEXITCODE = 1; return }
    # schemathesis.exe liegt im Python-Scripts-Verzeichnis (nicht auf PATH);
    # PATH-Vererbung nach Git-Bash ist unzuverlaessig -> absoluten Pfad als
    # Env durchreichen. WICHTIG: Forward-Slashes — Git-Bash interpretiert
    # 'C:\...' woertlich (Backslash = kein Pfadtrenner) -> 'No such file'.
    # Pfad robust ermitteln (User- vs. System-Install) statt hart zu kodieren.
    $schemaCmd = Get-Command schemathesis -ErrorAction SilentlyContinue
    $schemaBin = if ($schemaCmd) { $schemaCmd.Source }
        elseif (Test-Path "$env:APPDATA/Python/Python312/Scripts/schemathesis.exe") { "$env:APPDATA/Python/Python312/Scripts/schemathesis.exe" }
        elseif (Test-Path 'C:/Program Files/Python312/Scripts/schemathesis.exe') { 'C:/Program Files/Python312/Scripts/schemathesis.exe' }
        else { $null }
    if (-not $schemaBin) { Write-Host 'schemathesis.exe nicht gefunden (pip install -r requirements-dev.txt)'; $global:LASTEXITCODE = 1; return }
    # Forward-Slashes fuer Git-Bash (Backslash = kein Pfadtrenner).
    $env:SCHEMATHESIS_BIN = ($schemaBin -replace '\\','/')
    & $gitBash scripts/run_schemathesis.sh
}

Invoke-Stage 'e2e' {
    Push-Location (Join-Path $RepoRoot 'frontend')
    try { $env:BASE_URL = $FrontendUrl; npx playwright test --project=chromium }
    finally { Pop-Location }
}

Invoke-Stage 'a11y' {
    Push-Location (Join-Path $RepoRoot 'frontend')
    try { $env:BASE_URL = $FrontendUrl; npx playwright test --project=a11y }
    finally { Pop-Location }
}

Invoke-Stage 'vitest' {
    Push-Location (Join-Path $RepoRoot 'frontend')
    # Kein --reporter=basic: in Vitest 3 entfernt -> Startup Error
    try { npx vitest run }
    finally { Pop-Location }
}

Invoke-Stage 'monitor' {
    # Host-/Umgebungs-Alerts sind KEINE App-Regressionen: HostDiskSpaceLow
    # (Entwickler-Maschine, geteilt mit anderen Docker-Projekten) und die
    # Redis-Cache-/Latenz-Alerts (geteilte Dev-Redis mit riesigem Keyspace
    # anderer Projekte) bewerten nicht die Ablage-App. Der A-Z-Gate misst
    # App-Gesundheit -> diese Klassen werden ignoriert (separat dem Nutzer
    # gemeldet). Echte App-Alerts (Backend down, PostgreSQLDown, Celery,
    # Pipeline-SLOs) bleiben blockierend.
    $envAlerts = @('HostDiskSpaceLow','HostHighCpuLoad','HostOutOfMemory',
                   'HostHighSwapUsage','HostSwapUsageHigh',
                   'RedisLowCacheHitRate','RedisHighLatency','RedisRDBSnapshotFailed')
    $targets = curl.exe -s 'http://localhost:9090/api/v1/targets' | ConvertFrom-Json
    $down = $targets.data.activeTargets | Where-Object { $_.health -ne 'up' } | ForEach-Object { $_.labels.job }
    if ($down) { Write-Host "Targets DOWN: $($down -join ', ')"; $global:LASTEXITCODE = 1; return }
    $alerts = curl.exe -s 'http://localhost:9090/api/v1/alerts' | ConvertFrom-Json
    $firing = @($alerts.data.alerts | Where-Object { $_.state -eq 'firing' } | ForEach-Object { $_.labels.alertname } | Sort-Object -Unique)
    $envFiring = @($firing | Where-Object { $envAlerts -contains $_ })
    $appFiring = @($firing | Where-Object { $envAlerts -notcontains $_ })
    if ($envFiring) { Write-Host "Ignoriert (Host/Shared-Infra, KEINE App-Regression): $($envFiring -join ', ')" }
    if ($appFiring) { Write-Host "FIRING (App): $($appFiring -join ', ')"; $global:LASTEXITCODE = 1; return }
    curl.exe -fsS 'http://localhost:3002/api/health' | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Host 'Grafana-Health ROT'; return }
    Write-Host 'Monitoring gruen: alle Targets up, 0 App-Alerts firing.'
}

# --- Summary -----------------------------------------------------------------

if ($Results.Count -eq 0) {
    Write-Host "FEHLER: Keine Stufe ausgefuehrt - unbekannte Stage-Namen? ($($Stages -join ', '))" -ForegroundColor Red
    exit 1
}
$failed = @($Results.Values | Where-Object { $_.ExitCode -ne 0 })
$reportDir = Join-Path $RepoRoot 'docs/qa-reports'
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
$report = Join-Path $reportDir ("{0}-a-z-loop-{1}.md" -f $Stamp, $LoopId)
$lines = @(
    "# A-Z-Loop $LoopId — $RunStamp",
    "",
    "Branch: $(git rev-parse --abbrev-ref HEAD) @ $(git rev-parse --short HEAD)",
    "Stufen: $($Stages -join ', ')",
    "",
    "| Stufe | Ergebnis | Dauer (s) | Log |",
    "|-------|----------|-----------|-----|"
)
foreach ($r in $Results.Values) {
    $res = if ($r.ExitCode -eq 0) { 'GRUEN' } else { "ROT ($($r.ExitCode))" }
    $lines += "| $($r.Stage) | $res | $($r.Seconds) | $($r.Log) |"
}
$lines += ""
$lines += if ($failed.Count -eq 0) { "**Gesamtergebnis: GRUEN**" } else { "**Gesamtergebnis: ROT** — $($failed.Stage -join ', ')" }
$lines -join "`n" | Set-Content -Path $report -Encoding utf8
Write-Host "`nSummary: $report" -ForegroundColor Yellow
$Results.Values | Format-Table Stage, ExitCode, Seconds -AutoSize | Out-Host

exit $failed.Count
