#!/bin/bash
# =============================================================================
# Backend Watchdog - Sprint 0 / G05
# =============================================================================
# Zweck:  Periodischer Health-Check des Backend-Containers.
#         Bei N aufeinanderfolgenden Failures: Container restart + Slack-Alert.
#
# Aufruf:
#   - Manuell:        bash scripts/watchdog/backend_watchdog.sh
#   - Cron (Linux):   * * * * * /path/to/scripts/watchdog/backend_watchdog.sh
#   - Windows-Task:   Task Scheduler -> Trigger every 1min -> bash <pfad>
#   - Background:     nohup bash backend_watchdog.sh --loop &
#
# Voraussetzung:
#   - Slack-Webhook in infrastructure/alerting/slack-webhook.url
#     (Sprint 0 / G01 - placeholder durch echte URL ersetzen)
#
# Verhalten:
#   - 1 Failure -> Notify (warning, kein restart)
#   - 3 Failures in Folge -> docker-compose restart backend + Slack-Alert (critical)
#   - 5 Failures in Folge -> warnung an Ben "manueller Eingriff noetig"
#   - State-Datei: /tmp/ablage-backend-watchdog.state
# =============================================================================

set -uo pipefail  # KEIN -e: wir wollen weiterlaufen bei einzelnen Fehlern

# -- Configuration ------------------------------------------------------------
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly CONTAINER="${CONTAINER:-ablage-backend}"
readonly HEALTH_URL="${HEALTH_URL:-http://localhost:8000/health}"
readonly HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-15}"
readonly RESTART_THRESHOLD="${RESTART_THRESHOLD:-3}"
readonly ESCALATE_THRESHOLD="${ESCALATE_THRESHOLD:-5}"
readonly LOG_DIR="${LOG_DIR:-${REPO_ROOT}/scripts/watchdog/logs}"
readonly STATE_FILE="${STATE_FILE:-/tmp/ablage-backend-watchdog.state}"
readonly LOG_FILE="${LOG_DIR}/backend_watchdog.log"
# Sprint 0 / G05: SLACK_WEBHOOK_FILE ueber ENV ueberschreibbar (Sidecar nutzt /app/slack-webhook.url)
readonly SLACK_WEBHOOK_FILE="${SLACK_WEBHOOK_FILE:-${REPO_ROOT}/infrastructure/alerting/slack-webhook.url}"
readonly LOOP_INTERVAL="${LOOP_INTERVAL:-60}"  # Sekunden zwischen Iterationen im --loop Mode

mkdir -p "${LOG_DIR}"

# -- Logging ------------------------------------------------------------------
log() {
    local level="${1:-INFO}"
    local msg="${2:-}"
    local ts
    ts="$(date -Iseconds)"
    echo "[${ts}] [${level}] ${msg}" | tee -a "${LOG_FILE}"
}

# -- Slack Notification --------------------------------------------------------
send_slack() {
    local severity="${1:-info}"   # info | warning | critical
    local title="${2:-Backend Watchdog}"
    local text="${3:-no message}"

    if [ ! -f "${SLACK_WEBHOOK_FILE}" ]; then
        log WARN "Slack-Webhook-File fehlt: ${SLACK_WEBHOOK_FILE}"
        return 0
    fi

    local url
    url="$(head -n 1 "${SLACK_WEBHOOK_FILE}" | tr -d '[:space:]')"

    if [[ "${url}" == *"PLACEHOLDER"* ]] || [ -z "${url}" ]; then
        log WARN "Slack-Webhook ist Placeholder oder leer - Notification skipped (Sprint 0: G01 noch offen)"
        return 0
    fi

    local color emoji
    case "${severity}" in
        critical) color="danger";  emoji=":rotating_light:" ;;
        warning)  color="warning"; emoji=":warning:" ;;
        info)     color="good";    emoji=":information_source:" ;;
        *)        color="good";    emoji=":information_source:" ;;
    esac

    local hostname_=""
    hostname_="$(hostname 2>/dev/null || echo "unknown")"
    local payload
    payload=$(cat <<EOF
{
  "attachments": [{
    "color": "${color}",
    "title": "${emoji} ${title}",
    "text": "${text}",
    "fields": [
      {"title": "Container", "value": "${CONTAINER}", "short": true},
      {"title": "Host", "value": "${hostname_}", "short": true},
      {"title": "Severity", "value": "${severity}", "short": true},
      {"title": "Time", "value": "$(date -Iseconds)", "short": true}
    ],
    "footer": "Ablage-System Watchdog (Sprint 0 / G05)"
  }]
}
EOF
)

    if curl -sf -X POST "${url}" \
         -H 'Content-type: application/json' \
         --max-time 10 \
         -d "${payload}" >/dev/null 2>&1; then
        log INFO "Slack-Notification gesendet (${severity}): ${title}"
    else
        log WARN "Slack-Notification FEHLGESCHLAGEN"
    fi
}

# -- Health-Check --------------------------------------------------------------
# Returns 0 if healthy, 1 if unhealthy.
check_health() {
    if curl -sf -o /dev/null --max-time "${HEALTH_TIMEOUT}" "${HEALTH_URL}" 2>/dev/null; then
        return 0
    else
        return 1
    fi
}

# Container-Existenz pruefen (exakter Match per grep statt docker-Regex - cross-OS)
container_running() {
    docker ps --filter "name=${CONTAINER}" --format "{{.Names}}" 2>/dev/null | grep -qx "${CONTAINER}"
}

# -- State Management ---------------------------------------------------------
get_failure_count() {
    if [ -f "${STATE_FILE}" ]; then
        cat "${STATE_FILE}" 2>/dev/null || echo "0"
    else
        echo "0"
    fi
}

set_failure_count() {
    echo "$1" > "${STATE_FILE}"
}

# -- Container Restart --------------------------------------------------------
# Strategie:
#   1) Sidecar-Mode (SIDECAR_MODE=true): nutze `docker restart` via docker.sock
#      (kein docker-compose im Sidecar-Container)
#   2) Host-Mode: nutze `docker-compose restart` aus Repo-Root (Cron, manuell)
#   3) Fallback: `docker restart` direkt
restart_backend() {
    log WARN "Restarting container ${CONTAINER}"

    # Sidecar-Mode oder docker-compose nicht verfuegbar -> direkter docker restart
    if [ "${SIDECAR_MODE:-false}" = "true" ] || ! command -v docker-compose >/dev/null 2>&1; then
        if docker restart "${CONTAINER}" >> "${LOG_FILE}" 2>&1; then
            log INFO "docker restart erfolgreich (Sidecar-Mode=${SIDECAR_MODE:-false})"
            return 0
        else
            log ERROR "docker restart FEHLGESCHLAGEN"
            return 1
        fi
    fi

    # Host-Mode: docker-compose im Repo-Root
    if ! cd "${REPO_ROOT}"; then
        log ERROR "Cannot cd to ${REPO_ROOT}"
        return 1
    fi

    if docker-compose restart "${CONTAINER#ablage-}" >> "${LOG_FILE}" 2>&1; then
        log INFO "docker-compose restart erfolgreich"
        return 0
    else
        log ERROR "docker-compose restart FEHLGESCHLAGEN"
        return 1
    fi
}

# -- Single Iteration ----------------------------------------------------------
run_iteration() {
    local failure_count
    failure_count="$(get_failure_count)"

    if check_health; then
        if [ "${failure_count}" -gt "0" ]; then
            log INFO "Backend wieder healthy (war ${failure_count} Iterations down)"
            send_slack "info" "Backend Recovered" \
                "Backend ist wieder erreichbar nach ${failure_count} Failed Health-Checks."
            set_failure_count 0
        fi
        return 0
    fi

    # Failure path
    failure_count=$((failure_count + 1))
    set_failure_count "${failure_count}"

    log WARN "Health-Check FAILED (count=${failure_count}/${RESTART_THRESHOLD})"

    if [ "${failure_count}" -eq "1" ]; then
        # Erste Failure: nur loggen, kein restart (vielleicht transient)
        return 1
    fi

    if [ "${failure_count}" -eq "${RESTART_THRESHOLD}" ]; then
        log WARN "Threshold erreicht (${RESTART_THRESHOLD} Failures) - Restart Container"
        send_slack "critical" "Backend Down - Auto-Restart" \
            "Backend hat ${RESTART_THRESHOLD} Health-Checks in Folge versagt. Watchdog initiiert docker-compose restart. URL: ${HEALTH_URL}"
        restart_backend
        return 1
    fi

    if [ "${failure_count}" -ge "${ESCALATE_THRESHOLD}" ]; then
        log ERROR "Eskalation: ${failure_count} Failures - manueller Eingriff noetig"
        send_slack "critical" "Backend Down - MANUELLER EINGRIFF NOETIG" \
            "Backend ist seit ${failure_count} Iterationen down trotz Auto-Restart. Pruefe Logs: docker logs ${CONTAINER} | tail -50"
        return 1
    fi

    return 1
}

# -- Loop Mode ----------------------------------------------------------------
run_loop() {
    log INFO "Watchdog-Loop gestartet (interval=${LOOP_INTERVAL}s, container=${CONTAINER})"
    while true; do
        run_iteration || true
        sleep "${LOOP_INTERVAL}"
    done
}

# -- Status Mode --------------------------------------------------------------
show_status() {
    local failure_count
    failure_count="$(get_failure_count)"
    echo "=== Backend Watchdog Status ==="
    echo "Container:           ${CONTAINER}"
    echo "Health-URL:          ${HEALTH_URL}"
    echo "Restart-Threshold:   ${RESTART_THRESHOLD}"
    echo "Escalate-Threshold:  ${ESCALATE_THRESHOLD}"
    echo "Aktueller Failure-Count: ${failure_count}"
    echo "State-File:          ${STATE_FILE}"
    echo "Log-File:            ${LOG_FILE}"
    if container_running; then
        echo "Container-Status:    RUNNING"
    else
        echo "Container-Status:    NOT RUNNING"
    fi
    if check_health; then
        echo "Health-Check:        OK"
    else
        echo "Health-Check:        FAILED"
    fi
    if [ -f "${SLACK_WEBHOOK_FILE}" ]; then
        local url
        url="$(head -n 1 "${SLACK_WEBHOOK_FILE}" | tr -d '[:space:]')"
        if [[ "${url}" == *"PLACEHOLDER"* ]]; then
            echo "Slack-Webhook:       PLACEHOLDER (nicht aktiv - siehe SPRINT_0_OPEN.md)"
        else
            echo "Slack-Webhook:       konfiguriert"
        fi
    else
        echo "Slack-Webhook:       FEHLT"
    fi
}

# -- Reset Mode ---------------------------------------------------------------
reset_state() {
    set_failure_count 0
    log INFO "Failure-Count reset auf 0"
    echo "Reset done"
}

# -- Main ---------------------------------------------------------------------
case "${1:-once}" in
    once)
        run_iteration
        ;;
    --loop|-l|loop)
        run_loop
        ;;
    --status|status)
        show_status
        ;;
    --reset|reset)
        reset_state
        ;;
    --test-slack)
        send_slack "info" "Watchdog Test-Notification" \
            "Sprint 0 / G05 Watchdog Test. Wenn du das siehst, funktioniert Slack-Integration."
        ;;
    --help|-h|help)
        cat <<EOF
Backend Watchdog - Sprint 0 / G05

Usage: $0 [MODE]

MODES:
  once          Eine Health-Check-Iteration (default, fuer Cron)
  loop          Endlosschleife mit ${LOOP_INTERVAL}s Pause
  status        Zeige aktuellen Watchdog-State
  reset         Failure-Count auf 0 zuruecksetzen
  --test-slack  Sende Test-Notification an Slack
  help          Diese Hilfe

ENV-VARS:
  CONTAINER             (default: ablage-backend)
  HEALTH_URL            (default: http://localhost:8000/health)
  HEALTH_TIMEOUT        (default: 15s)
  RESTART_THRESHOLD     (default: 3 Failures bis Restart)
  ESCALATE_THRESHOLD    (default: 5 Failures bis Eskalation)
  LOOP_INTERVAL         (default: 60s)

CRON-Setup (alle 1 Minute):
  echo "* * * * * $(realpath "$0")" | crontab -

WINDOWS Task-Scheduler:
  Action: bash.exe
  Args:   "$(realpath "$0")"
  Trigger: every 1 minute
EOF
        ;;
    *)
        echo "Unknown mode: $1" >&2
        echo "Use --help for usage" >&2
        exit 2
        ;;
esac
