#!/bin/bash
# =============================================================================
# Master Backup Orchestrator for Ablage-System
# Runs all backup scripts sequentially with error tracking and reporting
# =============================================================================
set -euo pipefail

# -- Configuration (override via environment) ---------------------------------
BACKUP_BASE="${BACKUP_BASE:-/backup}"
LOG_DIR="${BACKUP_BASE}/logs"
LOG_FILE="${LOG_DIR}/backup_all.log"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Slack notification (optional)
SLACK_WEBHOOK_URL="${SLACK_WEBHOOK_URL:-}"

# -- Logging ------------------------------------------------------------------
mkdir -p "${LOG_DIR}" "${BACKUP_BASE}"
exec > >(tee -a "${LOG_FILE}") 2>&1

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] FEHLER: $1" >&2
}

# -- Notification helper -------------------------------------------------------
send_notification() {
    local status="$1"
    local message="$2"

    if [ -n "${SLACK_WEBHOOK_URL}" ]; then
        local color="good"
        local emoji=":white_check_mark:"
        if [ "${status}" = "FEHLER" ]; then
            color="danger"
            emoji=":x:"
        elif [ "${status}" = "WARNUNG" ]; then
            color="warning"
            emoji=":warning:"
        fi

        # Sanitize message for JSON
        local json_message
        json_message=$(echo "${message}" | sed 's/"/\\"/g' | sed ':a;N;$!ba;s/\n/\\n/g')

        curl -s -X POST "${SLACK_WEBHOOK_URL}" \
            -H 'Content-type: application/json' \
            -d "{
                \"attachments\": [{
                    \"color\": \"${color}\",
                    \"title\": \"${emoji} Ablage-System Backup: ${status}\",
                    \"text\": \"${json_message}\",
                    \"footer\": \"Ablage-System Backup\",
                    \"ts\": $(date +%s)
                }]
            }" >/dev/null 2>&1 || log "Slack-Benachrichtigung konnte nicht gesendet werden"
    fi
}

# -- Track results -------------------------------------------------------------
declare -A RESULTS
declare -A DURATIONS
TOTAL_ERRORS=0
OVERALL_START=$(date +%s)

run_backup() {
    local name="$1"
    local script="$2"
    local start_time
    start_time=$(date +%s)

    log "--- Starte ${name} ---"

    if [ ! -f "${script}" ]; then
        log_error "Script nicht gefunden: ${script}"
        RESULTS["${name}"]="FEHLER (Script nicht gefunden)"
        DURATIONS["${name}"]="0s"
        TOTAL_ERRORS=$((TOTAL_ERRORS + 1))
        return 1
    fi

    if [ ! -x "${script}" ]; then
        chmod +x "${script}"
    fi

    local exit_code=0
    bash "${script}" || exit_code=$?

    local end_time
    end_time=$(date +%s)
    local duration=$((end_time - start_time))
    DURATIONS["${name}"]="${duration}s"

    if [ "${exit_code}" -eq 0 ]; then
        RESULTS["${name}"]="ERFOLGREICH"
        log "--- ${name}: ERFOLGREICH (${duration}s) ---"
    else
        RESULTS["${name}"]="FEHLER (Exit-Code: ${exit_code})"
        TOTAL_ERRORS=$((TOTAL_ERRORS + 1))
        log_error "--- ${name}: FEHLGESCHLAGEN (Exit-Code: ${exit_code}, ${duration}s) ---"
    fi

    echo ""
    return "${exit_code}"
}

# -- Main execution ------------------------------------------------------------
log "================================================================"
log "=== Ablage-System Komplett-Backup gestartet ==="
log "================================================================"
log "Zeitstempel: ${TIMESTAMP}"
log "Basis-Verzeichnis: ${BACKUP_BASE}"
log ""

# 1. PostgreSQL Backup
PG_EXIT=0
run_backup "PostgreSQL" "${SCRIPT_DIR}/pg_backup.sh" || PG_EXIT=$?

# 2. MinIO Backup
MINIO_EXIT=0
run_backup "MinIO" "${SCRIPT_DIR}/minio_backup.sh" || MINIO_EXIT=$?

# 3. Redis Backup
REDIS_EXIT=0
run_backup "Redis" "${SCRIPT_DIR}/redis_backup.sh" || REDIS_EXIT=$?

# 4. Docker Volumes Backup
VOLUME_EXIT=0
run_backup "Docker-Volumes" "${SCRIPT_DIR}/volume_backup.sh" || VOLUME_EXIT=$?

# -- Calculate totals ----------------------------------------------------------
OVERALL_END=$(date +%s)
OVERALL_DURATION=$((OVERALL_END - OVERALL_START))
OVERALL_MINUTES=$((OVERALL_DURATION / 60))
OVERALL_SECONDS=$((OVERALL_DURATION % 60))

# Calculate total backup size
TOTAL_SIZE=$(du -sh "${BACKUP_BASE}" 2>/dev/null | cut -f1)

# Individual directory sizes
PG_SIZE=$(du -sh "${BACKUP_BASE}/postgres" 2>/dev/null | cut -f1 || echo "N/A")
MINIO_SIZE=$(du -sh "${BACKUP_BASE}/minio" 2>/dev/null | cut -f1 || echo "N/A")
REDIS_SIZE=$(du -sh "${BACKUP_BASE}/redis" 2>/dev/null | cut -f1 || echo "N/A")
VOLUME_SIZE=$(du -sh "${BACKUP_BASE}/volumes" 2>/dev/null | cut -f1 || echo "N/A")

# -- Generate summary report ---------------------------------------------------
log ""
log "================================================================"
log "=== BACKUP-ZUSAMMENFASSUNG ==="
log "================================================================"
log ""
log "Zeitpunkt:       $(date '+%Y-%m-%d %H:%M:%S')"
log "Gesamtdauer:     ${OVERALL_MINUTES}m ${OVERALL_SECONDS}s"
log "Gesamtgroesse:   ${TOTAL_SIZE}"
log ""
log "Ergebnisse:"
log "  PostgreSQL:    ${RESULTS[PostgreSQL]:-UEBERSPRUNGEN} (${DURATIONS[PostgreSQL]:-N/A}, ${PG_SIZE})"
log "  MinIO:         ${RESULTS[MinIO]:-UEBERSPRUNGEN} (${DURATIONS[MinIO]:-N/A}, ${MINIO_SIZE})"
log "  Redis:         ${RESULTS[Redis]:-UEBERSPRUNGEN} (${DURATIONS[Redis]:-N/A}, ${REDIS_SIZE})"
log "  Docker-Vol.:   ${RESULTS[Docker-Volumes]:-UEBERSPRUNGEN} (${DURATIONS[Docker-Volumes]:-N/A}, ${VOLUME_SIZE})"
log ""

if [ "${TOTAL_ERRORS}" -eq 0 ]; then
    STATUS="ERFOLGREICH"
    log "Status: Alle Backups erfolgreich abgeschlossen"
else
    STATUS="FEHLER"
    log_error "Status: ${TOTAL_ERRORS} von 4 Backups fehlgeschlagen"
fi

log "================================================================"

# -- Write summary to file -----------------------------------------------------
SUMMARY_FILE="${BACKUP_BASE}/logs/backup_summary_${TIMESTAMP}.txt"
{
    echo "Ablage-System Backup-Bericht"
    echo "============================"
    echo ""
    echo "Zeitpunkt:     $(date '+%Y-%m-%d %H:%M:%S')"
    echo "Gesamtdauer:   ${OVERALL_MINUTES}m ${OVERALL_SECONDS}s"
    echo "Gesamtgroesse: ${TOTAL_SIZE}"
    echo "Status:        ${STATUS}"
    echo ""
    echo "Ergebnisse:"
    echo "  PostgreSQL:    ${RESULTS[PostgreSQL]:-UEBERSPRUNGEN} (${DURATIONS[PostgreSQL]:-N/A}, ${PG_SIZE})"
    echo "  MinIO:         ${RESULTS[MinIO]:-UEBERSPRUNGEN} (${DURATIONS[MinIO]:-N/A}, ${MINIO_SIZE})"
    echo "  Redis:         ${RESULTS[Redis]:-UEBERSPRUNGEN} (${DURATIONS[Redis]:-N/A}, ${REDIS_SIZE})"
    echo "  Docker-Vol.:   ${RESULTS[Docker-Volumes]:-UEBERSPRUNGEN} (${DURATIONS[Docker-Volumes]:-N/A}, ${VOLUME_SIZE})"
    echo ""
    echo "Fehler gesamt: ${TOTAL_ERRORS}"
} > "${SUMMARY_FILE}"

log "Bericht gespeichert: ${SUMMARY_FILE}"

# -- Send notification ---------------------------------------------------------
NOTIFICATION_MSG="Zeitpunkt: $(date '+%Y-%m-%d %H:%M:%S')
Dauer: ${OVERALL_MINUTES}m ${OVERALL_SECONDS}s
Groesse: ${TOTAL_SIZE}

PostgreSQL: ${RESULTS[PostgreSQL]:-UEBERSPRUNGEN} (${DURATIONS[PostgreSQL]:-N/A})
MinIO: ${RESULTS[MinIO]:-UEBERSPRUNGEN} (${DURATIONS[MinIO]:-N/A})
Redis: ${RESULTS[Redis]:-UEBERSPRUNGEN} (${DURATIONS[Redis]:-N/A})
Docker-Volumes: ${RESULTS[Docker-Volumes]:-UEBERSPRUNGEN} (${DURATIONS[Docker-Volumes]:-N/A})"

send_notification "${STATUS}" "${NOTIFICATION_MSG}"

# -- Exit with appropriate code ------------------------------------------------
if [ "${TOTAL_ERRORS}" -gt 0 ]; then
    exit 1
fi

exit 0
