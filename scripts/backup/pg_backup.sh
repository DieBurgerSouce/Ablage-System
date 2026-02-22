#!/usr/bin/env bash
# =============================================================================
# PostgreSQL Backup Script - Ablage-System
# Taegliches Backup mit Retention-Management (7 taeglich, 4 woechentlich, 3 monatlich)
# =============================================================================
set -euo pipefail

# --- Configuration (environment variables with defaults from docker-compose) ---
CONTAINER_NAME="${PG_CONTAINER_NAME:-ablage-postgres}"
POSTGRES_DB="${POSTGRES_DB:-ablage_system}"
POSTGRES_USER="${POSTGRES_USER:-ablage_admin}"
# POSTGRES_PASSWORD / DB_PASSWORD must be set in environment or .env
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-${DB_PASSWORD:-}}"

BACKUP_DIR="${BACKUP_DIR:-/backup/postgres}"
LOG_DIR="${LOG_DIR:-/backup/logs}"
LOG_FILE="${LOG_DIR}/pg_backup.log"

# Retention policy
DAILY_RETENTION="${DAILY_RETENTION:-7}"
WEEKLY_RETENTION="${WEEKLY_RETENTION:-4}"
MONTHLY_RETENTION="${MONTHLY_RETENTION:-3}"

# --- Timestamps ---
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
DATE_DAY=$(date +"%Y%m%d")
DAY_OF_WEEK=$(date +"%u")  # 1=Monday, 7=Sunday
DAY_OF_MONTH=$(date +"%d")

# --- Helper Functions ---

log() {
    local level="$1"
    shift
    local msg="$*"
    local ts
    ts=$(date +"%Y-%m-%d %H:%M:%S")
    echo "[${ts}] [${level}] ${msg}" | tee -a "${LOG_FILE}"
}

die() {
    log "ERROR" "$*"
    # Fehler: Backup fehlgeschlagen
    log "ERROR" "Backup fehlgeschlagen - siehe Log fuer Details: ${LOG_FILE}"
    exit 1
}

ensure_dirs() {
    mkdir -p "${BACKUP_DIR}/daily"
    mkdir -p "${BACKUP_DIR}/weekly"
    mkdir -p "${BACKUP_DIR}/monthly"
    mkdir -p "${LOG_DIR}"
}

check_prerequisites() {
    # Check if docker is available
    if ! command -v docker &>/dev/null; then
        die "Docker ist nicht installiert oder nicht im PATH"
    fi

    # Check if container is running
    if ! docker inspect --format='{{.State.Running}}' "${CONTAINER_NAME}" 2>/dev/null | grep -q "true"; then
        die "Container '${CONTAINER_NAME}' laeuft nicht"
    fi

    # Check if password is set
    if [[ -z "${POSTGRES_PASSWORD}" ]]; then
        die "Kein Datenbank-Passwort gesetzt (POSTGRES_PASSWORD oder DB_PASSWORD)"
    fi
}

# --- Backup Function ---

create_backup() {
    local backup_type="$1"  # daily, weekly, monthly
    local backup_file="${BACKUP_DIR}/${backup_type}/${POSTGRES_DB}_${backup_type}_${TIMESTAMP}.sql.gz"

    log "INFO" "Starte ${backup_type} Backup: ${POSTGRES_DB} -> ${backup_file}"

    # Run pg_dump inside the container, pipe through gzip on host
    if docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${CONTAINER_NAME}" \
        pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
        --format=custom \
        --verbose \
        --no-owner \
        --no-privileges \
        --compress=6 \
        2>>"${LOG_FILE}" \
        > "${backup_file}"; then
        log "INFO" "Backup erstellt: ${backup_file}"
    else
        die "pg_dump fehlgeschlagen fuer ${backup_type} Backup"
    fi

    # Verify backup integrity
    verify_backup "${backup_file}"

    # Log file size
    local size
    size=$(du -h "${backup_file}" | cut -f1)
    log "INFO" "Backup-Groesse: ${size}"

    echo "${backup_file}"
}

# --- Verification Function ---

verify_backup() {
    local backup_file="$1"

    log "INFO" "Verifiziere Backup: ${backup_file}"

    # Check file exists and is not empty
    if [[ ! -s "${backup_file}" ]]; then
        die "Backup-Datei ist leer oder existiert nicht: ${backup_file}"
    fi

    # Use pg_restore --list to verify the archive is valid
    # We copy the file into the container for verification
    if docker exec -i "${CONTAINER_NAME}" pg_restore --list < "${backup_file}" > /dev/null 2>>"${LOG_FILE}"; then
        log "INFO" "Backup-Integritaet verifiziert: OK"
    else
        die "Backup-Integritaet fehlgeschlagen: ${backup_file}"
    fi
}

# --- Retention Management ---

cleanup_old_backups() {
    local backup_type="$1"
    local retention="$2"
    local target_dir="${BACKUP_DIR}/${backup_type}"

    log "INFO" "Bereinige ${backup_type} Backups (behalte letzte ${retention})"

    # Count existing backups
    local count
    count=$(find "${target_dir}" -name "*.sql.gz" -type f 2>/dev/null | wc -l)

    if (( count > retention )); then
        local to_delete=$(( count - retention ))
        log "INFO" "Loesche ${to_delete} alte ${backup_type} Backups"

        # Delete oldest files (sorted by modification time)
        find "${target_dir}" -name "*.sql.gz" -type f -printf '%T+ %p\n' \
            | sort \
            | head -n "${to_delete}" \
            | awk '{print $2}' \
            | while read -r file; do
                log "INFO" "Loesche: ${file}"
                rm -f "${file}"
            done
    else
        log "INFO" "Keine Bereinigung noetig (${count}/${retention} Backups vorhanden)"
    fi
}

# --- WAL Archiving Status ---

check_wal_status() {
    log "INFO" "Pruefe WAL-Archivierung..."

    local wal_level
    wal_level=$(docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${CONTAINER_NAME}" \
        psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -t -c "SHOW wal_level;" 2>/dev/null | tr -d ' ')

    log "INFO" "WAL Level: ${wal_level}"

    local wal_size
    wal_size=$(docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${CONTAINER_NAME}" \
        psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -t -c "SHOW wal_keep_size;" 2>/dev/null | tr -d ' ')

    log "INFO" "WAL Keep Size: ${wal_size}"

    # Get current WAL position
    local wal_lsn
    wal_lsn=$(docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${CONTAINER_NAME}" \
        psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -t -c "SELECT pg_current_wal_lsn();" 2>/dev/null | tr -d ' ')

    log "INFO" "Aktuelle WAL Position: ${wal_lsn}"
}

# --- Main ---

main() {
    log "INFO" "=========================================="
    log "INFO" "PostgreSQL Backup gestartet"
    log "INFO" "=========================================="

    ensure_dirs
    check_prerequisites
    check_wal_status

    # Always create daily backup
    local backup_file
    backup_file=$(create_backup "daily")
    cleanup_old_backups "daily" "${DAILY_RETENTION}"

    # Weekly backup on Sunday (day 7)
    if [[ "${DAY_OF_WEEK}" == "7" ]]; then
        log "INFO" "Sonntag erkannt - erstelle woechentliches Backup"
        cp "${backup_file}" "${BACKUP_DIR}/weekly/${POSTGRES_DB}_weekly_${TIMESTAMP}.sql.gz"
        verify_backup "${BACKUP_DIR}/weekly/${POSTGRES_DB}_weekly_${TIMESTAMP}.sql.gz"
        cleanup_old_backups "weekly" "${WEEKLY_RETENTION}"
    fi

    # Monthly backup on the 1st
    if [[ "${DAY_OF_MONTH}" == "01" ]]; then
        log "INFO" "Monatserster erkannt - erstelle monatliches Backup"
        cp "${backup_file}" "${BACKUP_DIR}/monthly/${POSTGRES_DB}_monthly_${TIMESTAMP}.sql.gz"
        verify_backup "${BACKUP_DIR}/monthly/${POSTGRES_DB}_monthly_${TIMESTAMP}.sql.gz"
        cleanup_old_backups "monthly" "${MONTHLY_RETENTION}"
    fi

    # Summary
    local total_daily total_weekly total_monthly
    total_daily=$(find "${BACKUP_DIR}/daily" -name "*.sql.gz" -type f 2>/dev/null | wc -l)
    total_weekly=$(find "${BACKUP_DIR}/weekly" -name "*.sql.gz" -type f 2>/dev/null | wc -l)
    total_monthly=$(find "${BACKUP_DIR}/monthly" -name "*.sql.gz" -type f 2>/dev/null | wc -l)

    log "INFO" "=========================================="
    log "INFO" "Backup-Zusammenfassung:"
    log "INFO" "  Taeglich:   ${total_daily}/${DAILY_RETENTION}"
    log "INFO" "  Woechentlich: ${total_weekly}/${WEEKLY_RETENTION}"
    log "INFO" "  Monatlich:  ${total_monthly}/${MONTHLY_RETENTION}"
    log "INFO" "Backup erfolgreich abgeschlossen"
    log "INFO" "=========================================="

    exit 0
}

main "$@"
