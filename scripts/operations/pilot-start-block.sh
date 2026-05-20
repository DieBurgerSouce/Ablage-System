#!/usr/bin/env bash
# =============================================================================
# Pilot-Start-Block Triage Script
# Goal: .claude/reviews/2026-05-20/GOAL_PILOT_START_BLOCK.md
# Voraussetzung: Docker-Stack laeuft, sprint-0-pilot-hardening gemerged
# =============================================================================
#
# Usage:
#   bash scripts/operations/pilot-start-block.sh status    # nur Snapshot, kein Fix
#   bash scripts/operations/pilot-start-block.sh reload    # Prometheus reload (2x)
#   bash scripts/operations/pilot-start-block.sh sentry    # Sentry verify
#   bash scripts/operations/pilot-start-block.sh full      # alle Steps nacheinander
#
# Idempotent: Status-Checks koennen beliebig oft laufen.
# Destructiv: Nur "reload" aendert Prometheus-State (sicher).
# =============================================================================

set -euo pipefail

PROMETHEUS_URL="${PROMETHEUS_URL:-http://localhost:9090}"
ALERTMANAGER_URL="${ALERTMANAGER_URL:-http://localhost:9093}"
BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
DOCS_DIR="docs/operations"
TRIAGE_FILE="${DOCS_DIR}/alert-triage-2026-05-20.md"

# =============================================================================
# Helpers
# =============================================================================

log_info()  { echo "[INFO]  $*" >&2; }
log_warn()  { echo "[WARN]  $*" >&2; }
log_error() { echo "[ERROR] $*" >&2; }
log_ok()    { echo "[OK]    $*" >&2; }

require_cmd() {
  for cmd in "$@"; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
      log_error "Befehl nicht gefunden: $cmd"
      return 1
    fi
  done
}

check_docker_alive() {
  if ! docker ps >/dev/null 2>&1; then
    log_error "Docker-Daemon nicht erreichbar. Pilot-Start-Block ist blockiert."
    log_error "Fix: PowerShell admin -> 'wsl --shutdown' -> Docker Desktop neu starten."
    return 1
  fi
}

# =============================================================================
# Step 1: Snapshot
# =============================================================================

step_snapshot() {
  require_cmd curl jq docker docker-compose
  check_docker_alive

  log_info "=== Snapshot der laufenden Container ==="
  docker ps --filter "name=ablage" --format "table {{.Names}}\t{{.Status}}"

  log_info ""
  log_info "=== Aktuell feuernde Alerts ==="
  local firing_count
  firing_count="$(curl -sf "${PROMETHEUS_URL}/api/v1/alerts" \
    | jq '[.data.alerts[] | select(.state=="firing")] | length')"
  log_info "Anzahl firing Alerts: ${firing_count}"

  curl -sf "${PROMETHEUS_URL}/api/v1/alerts" \
    | jq '.data.alerts[] | select(.state=="firing") | {alertname, severity:.labels.severity, activeAt, summary:.annotations.summary}'

  log_info ""
  log_info "=== Letzte 50 Error-Lines aus Kernservices ==="
  docker-compose logs --tail=50 backend worker ocr-deepseek 2>&1 \
    | grep -iE "error|fatal|down" | tail -30 || log_warn "Keine Errors gefunden (gut)"
}

# =============================================================================
# Step 2: Prometheus Reload (False-Positive-Fix)
# =============================================================================

step_reload() {
  require_cmd curl
  check_docker_alive

  log_info "=== Prometheus Rule-Reload (2x, Lesson aus Commit 438f2486) ==="
  for i in 1 2; do
    log_info "Reload-Attempt ${i}..."
    if curl -sfX POST "${PROMETHEUS_URL}/-/reload"; then
      log_ok "Reload ${i} erfolgreich"
    else
      log_error "Reload ${i} fehlgeschlagen"
      return 1
    fi
    sleep 2
  done

  log_info ""
  log_info "Nach Reload: erneuter Status-Check"
  step_snapshot
}

# =============================================================================
# Step 3: Sentry Smoke-Test
# =============================================================================

step_sentry() {
  require_cmd curl docker grep
  check_docker_alive

  log_info "=== Sentry-Initialisierungsstatus im Backend ==="
  if docker logs ablage-backend 2>&1 | grep -q "sentry_initialized"; then
    log_ok "sentry_initialized gefunden"
  elif docker logs ablage-backend 2>&1 | grep -q "sentry_not_configured"; then
    log_error "sentry_not_configured - SENTRY_DSN fehlt in .env oder Backend nicht rebuilded"
    log_error "Fix: .env mit SENTRY_DSN setzen, dann 'docker-compose build backend && docker-compose up -d backend'"
    return 1
  else
    log_warn "Weder sentry_initialized noch sentry_not_configured gefunden - Backend startet noch?"
  fi

  log_info ""
  log_info "=== Test-Error fuer Sentry-Inbox provozieren ==="
  local http_code
  http_code="$(curl -s -o /dev/null -w "%{http_code}" "${BACKEND_URL}/api/v1/this-does-not-exist")"
  log_info "HTTP-Code: ${http_code} (404 erwartet)"
  log_info "Pruefe in https://sentry.io/issues/ ob der Error innerhalb 30s erscheint."
}

# =============================================================================
# Step 4: Recommended Silences fuer 5 NEEDS_VERIFY (Code bereits gefixt)
# =============================================================================

step_show_silences() {
  log_info "=== Empfohlene amtool-Silences fuer NEEDS_VERIFY Alerts ==="
  log_info "Diese 5 Alerts sind im Code bereits gefixt (siehe MERGE_CONFLICT_ANALYSIS"
  log_info "+ Commits 438f2486, 6de2d89e). Falls sie nach Reload noch firen,"
  log_info "Silence fuer 24h damit Triage in Ruhe gemacht werden kann."
  log_info ""
  cat <<'EOF'
# RedisReplicationBroken - Single-Node, Rule auskommentiert
amtool silence add --duration=24h \
  --author="ben" \
  --comment="Single-Node, Rule auskommentiert in redis-alerts.yml:148-153" \
  alertname=RedisReplicationBroken

# LokiCompactorNotRunning - echter Metric in 6de2d89e gefixt
amtool silence add --duration=24h \
  --author="ben" \
  --comment="Metric-Name gefixt in loki-alerts.yml:71-72 (Commit 6de2d89e)" \
  alertname=LokiCompactorNotRunning

# QdrantDown - Bearer-Token-File gemountet
amtool silence add --duration=24h \
  --author="ben" \
  --comment="bearer_token_file in prometheus.yml:125 + Token-File vorhanden (438f2486)" \
  alertname=QdrantDown

# APIDown - start_period 600s in docker-compose.yml
amtool silence add --duration=24h \
  --author="ben" \
  --comment="Backend healthcheck start_period 600s gesetzt (Sprint-0/G05)" \
  alertname=APIDown

# CeleryWorkerDownLong - HTTP-Check via curl/pgrep
amtool silence add --duration=24h \
  --author="ben" \
  --comment="Healthcheck umgestellt auf curl /metrics + pgrep (438f2486, docker-compose.yml:801)" \
  alertname=CeleryWorkerDownLong
EOF
}

# =============================================================================
# Step 5: TBD-Triage (4 echte Untersuchungen)
# =============================================================================

step_tbd_triage() {
  require_cmd docker
  check_docker_alive

  log_info "=== TBD-Alerts: 4 echte Untersuchungen ==="
  log_info ""

  log_info "--- OCRBackendDown: Container + GPU ---"
  docker ps --filter "name=ocr" --format "table {{.Names}}\t{{.Status}}\t{{.Health}}"
  if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv,noheader
  else
    log_warn "nvidia-smi nicht verfuegbar (kein GPU oder Host-Tool fehlt)"
  fi
  log_info ""

  log_info "--- ServiceDown: nur als Aggregat? ---"
  log_info "Wenn andere Down-Alerts gefixt sind, sollte ServiceDown auto-resolven."
  log_info ""

  log_info "--- HostHighSwapUsage: RAM-Druck? ---"
  free -h 2>/dev/null || log_warn "free -h nicht verfuegbar (Windows? Nutze Task-Manager)"
  log_info ""

  log_info "--- HostDiskSpaceLow: ---"
  df -h 2>/dev/null | head -10 || log_warn "df -h nicht verfuegbar (Windows? Nutze 'Get-PSDrive')"
  log_warn "Bei C:-Disk-Knappheit: 'docker system prune -a' WARNUNG - andere Projekte (Trellis, ComfyUI, TTS-Stack, clawdbot) betroffen. USER-APPROVAL einholen!"
}

# =============================================================================
# Main Dispatcher
# =============================================================================

main() {
  local cmd="${1:-help}"

  case "$cmd" in
    status)     step_snapshot ;;
    reload)     step_reload ;;
    sentry)     step_sentry ;;
    silences)   step_show_silences ;;
    tbd)        step_tbd_triage ;;
    full)
      step_snapshot
      echo ""
      step_reload
      echo ""
      step_sentry
      echo ""
      step_show_silences
      echo ""
      step_tbd_triage
      ;;
    help|--help|-h|*)
      cat <<EOF
Pilot-Start-Block Triage Script

Usage: bash $0 <command>

Commands:
  status    Snapshot der Container + firing Alerts + Error-Logs
  reload    Prometheus Rule-Reload (2x, dann erneuter Status)
  sentry    Sentry-Init-Status pruefen + Test-Error provozieren
  silences  Empfohlene amtool-Silences anzeigen (Copy-Paste)
  tbd       Daten fuer die 4 TBD-Alerts (OCR/Service/Swap/Disk)
  full      Alle obigen Steps nacheinander

Beispiel-Workflow:
  bash $0 status     # Erstmal sehen was los ist
  bash $0 reload     # Prometheus reloaden (False-Positives weg)
  bash $0 status     # Erneut sehen, was uebrig bleibt
  bash $0 sentry     # Sentry verify (nur wenn DSN gesetzt)
  bash $0 silences   # Copy-Paste Silences fuer NEEDS_VERIFY
  bash $0 tbd        # Daten fuer echte Probleme sammeln
EOF
      ;;
  esac
}

main "$@"
