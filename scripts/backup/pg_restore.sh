#!/usr/bin/env bash
# =============================================================================
# PostgreSQL Restore Script - Ablage-System
# Wiederherstellung aus Backup-Dateien mit Sicherheitspruefungen
# =============================================================================
set -euo pipefail

# --- Configuration ---
CONTAINER_NAME="${PG_CONTAINER_NAME:-ablage-postgres}"
POSTGRES_DB="${POSTGRES_DB:-ablage_system}"
POSTGRES_USER="${POSTGRES_USER:-ablage_admin}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-${DB_PASSWORD:-}}"

BACKUP_DIR="${BACKUP_DIR:-/backup/postgres}"
LOG_DIR="${LOG_DIR:-/backup/logs}"
LOG_FILE="${LOG_DIR}/pg_restore.log"

# --- Parse Arguments ---
DRY_RUN=false
USE_LATEST=false
BACKUP_FILE=""
FORCE=false

usage() {
    cat <<EOF
Verwendung: $0 [OPTIONEN] [BACKUP_DATEI]

PostgreSQL Datenbank-Wiederherstellung fuer Ablage-System.

Optionen:
  --latest      Neuestes Backup automatisch auswaehlen
  --dry-run     Backup nur verifizieren, nicht wiederherstellen
  --force       Sicherheitsabfrage ueberspringen
  -h, --help    Diese Hilfe anzeigen

Beispiele:
  $0 /backup/postgres/daily/ablage_system_daily_20260222.sql.gz
  $0 --latest
  $0 --latest --dry-run
  $0 --latest --force

Umgebungsvariablen:
  PG_CONTAINER_NAME   Docker-Container (default: ablage-postgres)
  POSTGRES_DB          Datenbankname (default: ablage_system)
  POSTGRES_USER        Benutzer (default: ablage_admin)
  POSTGRES_PASSWORD    Passwort (oder DB_PASSWORD)
  BACKUP_DIR           Backup-Verzeichnis (default: /backup/postgres)
EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --latest)
            USE_LATEST=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --force)
            FORCE=true
            shift
            ;;
        -h|--help)
            usage
            ;;
        -*)
            echo "Unbekannte Option: $1" >&2
            usage
            ;;
        *)
            BACKUP_FILE="$1"
            shift
            ;;
    esac
done

# --- Helper Functions ---

log() {
    local level="$1"
    shift
    local msg="$*"
    local ts
    ts=$(date +"%Y-%m-%d %H:%M:%S")
    mkdir -p "${LOG_DIR}"
    echo "[${ts}] [${level}] ${msg}" | tee -a "${LOG_FILE}"
}

die() {
    log "ERROR" "$*"
    exit 1
}

check_prerequisites() {
    if ! command -v docker &>/dev/null; then
        die "Docker ist nicht installiert oder nicht im PATH"
    fi

    if ! docker inspect --format='{{.State.Running}}' "${CONTAINER_NAME}" 2>/dev/null | grep -q "true"; then
        die "Container '${CONTAINER_NAME}' laeuft nicht"
    fi

    if [[ -z "${POSTGRES_PASSWORD}" ]]; then
        die "Kein Datenbank-Passwort gesetzt (POSTGRES_PASSWORD oder DB_PASSWORD)"
    fi
}

find_latest_backup() {
    local latest=""

    # Search across all backup types, pick the most recent file
    latest=$(find "${BACKUP_DIR}" -name "*.sql.gz" -type f -printf '%T@ %p\n' 2>/dev/null \
        | sort -rn \
        | head -1 \
        | awk '{print $2}')

    if [[ -z "${latest}" ]]; then
        die "Kein Backup gefunden in ${BACKUP_DIR}"
    fi

    echo "${latest}"
}

verify_backup() {
    local file="$1"

    log "INFO" "Verifiziere Backup: ${file}"

    if [[ ! -f "${file}" ]]; then
        die "Backup-Datei nicht gefunden: ${file}"
    fi

    if [[ ! -s "${file}" ]]; then
        die "Backup-Datei ist leer: ${file}"
    fi

    # Verify archive with pg_restore --list
    if docker exec -i "${CONTAINER_NAME}" pg_restore --list < "${file}" > /dev/null 2>>"${LOG_FILE}"; then
        log "INFO" "Backup-Integritaet: OK"
        return 0
    else
        die "Backup-Datei ist beschaedigt oder ungueltig: ${file}"
    fi
}

get_backup_info() {
    local file="$1"

    local size
    size=$(du -h "${file}" | cut -f1)
    local modified
    modified=$(date -r "${file}" +"%Y-%m-%d %H:%M:%S" 2>/dev/null || stat -c "%y" "${file}" 2>/dev/null | cut -d. -f1)

    # Count objects in the backup
    local object_count
    object_count=$(docker exec -i "${CONTAINER_NAME}" pg_restore --list < "${file}" 2>/dev/null | wc -l)

    log "INFO" "Backup-Details:"
    log "INFO" "  Datei:     ${file}"
    log "INFO" "  Groesse:   ${size}"
    log "INFO" "  Datum:     ${modified}"
    log "INFO" "  Objekte:   ${object_count}"
}

confirm_restore() {
    if [[ "${FORCE}" == "true" ]]; then
        return 0
    fi

    echo ""
    echo "=========================================="
    echo "  WARNUNG: Datenbank-Wiederherstellung"
    echo "=========================================="
    echo ""
    echo "  Datenbank:  ${POSTGRES_DB}"
    echo "  Container:  ${CONTAINER_NAME}"
    echo "  Backup:     ${BACKUP_FILE}"
    echo ""
    echo "  ALLE bestehenden Daten werden UEBERSCHRIEBEN!"
    echo ""
    echo -n "  Fortfahren? (ja/nein): "
    read -r answer

    if [[ "${answer}" != "ja" ]]; then
        log "INFO" "Wiederherstellung vom Benutzer abgebrochen"
        exit 0
    fi
}

# --- Restore Function ---

perform_restore() {
    local file="$1"

    log "INFO" "Starte Wiederherstellung von: ${file}"

    # Create a pre-restore backup (safety net)
    local safety_backup="${BACKUP_DIR}/pre_restore_${POSTGRES_DB}_$(date +%Y%m%d_%H%M%S).sql.gz"
    log "INFO" "Erstelle Sicherheitsbackup vor Wiederherstellung: ${safety_backup}"

    if docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${CONTAINER_NAME}" \
        pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
        --format=custom --compress=6 \
        2>>"${LOG_FILE}" \
        > "${safety_backup}"; then
        log "INFO" "Sicherheitsbackup erstellt: ${safety_backup}"
    else
        log "WARN" "Sicherheitsbackup fehlgeschlagen - fahre trotzdem fort"
    fi

    # Terminate existing connections to the database
    log "INFO" "Beende bestehende Verbindungen zur Datenbank..."
    docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${CONTAINER_NAME}" \
        psql -U "${POSTGRES_USER}" -d postgres -c \
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${POSTGRES_DB}' AND pid <> pg_backend_pid();" \
        2>>"${LOG_FILE}" || true

    # Drop and recreate the database
    log "INFO" "Loesche und erstelle Datenbank neu..."
    docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${CONTAINER_NAME}" \
        psql -U "${POSTGRES_USER}" -d postgres -c \
        "DROP DATABASE IF EXISTS \"${POSTGRES_DB}\";" \
        2>>"${LOG_FILE}"

    docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${CONTAINER_NAME}" \
        psql -U "${POSTGRES_USER}" -d postgres -c \
        "CREATE DATABASE \"${POSTGRES_DB}\" OWNER \"${POSTGRES_USER}\";" \
        2>>"${LOG_FILE}"

    # Ensure pgvector extension exists
    docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${CONTAINER_NAME}" \
        psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -c \
        "CREATE EXTENSION IF NOT EXISTS vector;" \
        2>>"${LOG_FILE}" || true

    # Restore from backup
    log "INFO" "Stelle Datenbank wieder her..."
    if docker exec -i -e PGPASSWORD="${POSTGRES_PASSWORD}" "${CONTAINER_NAME}" \
        pg_restore -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
        --no-owner \
        --no-privileges \
        --verbose \
        --exit-on-error \
        < "${file}" \
        2>>"${LOG_FILE}"; then
        log "INFO" "Wiederherstellung erfolgreich abgeschlossen"
    else
        log "ERROR" "Wiederherstellung fehlgeschlagen!"
        log "INFO" "Sicherheitsbackup verfuegbar: ${safety_backup}"
        die "pg_restore fehlgeschlagen - Sicherheitsbackup: ${safety_backup}"
    fi

    # Verify restored database
    log "INFO" "Verifiziere wiederhergestellte Datenbank..."
    local table_count
    table_count=$(docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${CONTAINER_NAME}" \
        psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -t -c \
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';" \
        2>/dev/null | tr -d ' ')

    log "INFO" "Wiederhergestellte Tabellen: ${table_count}"

    # Run ANALYZE to update statistics
    log "INFO" "Aktualisiere Datenbank-Statistiken (ANALYZE)..."
    docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${CONTAINER_NAME}" \
        psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -c "ANALYZE;" \
        2>>"${LOG_FILE}"

    log "INFO" "Wiederherstellung vollstaendig abgeschlossen"
}

# --- Main ---

main() {
    log "INFO" "=========================================="
    log "INFO" "PostgreSQL Restore gestartet"
    log "INFO" "=========================================="

    check_prerequisites

    # Determine backup file
    if [[ "${USE_LATEST}" == "true" ]]; then
        BACKUP_FILE=$(find_latest_backup)
        log "INFO" "Neuestes Backup ausgewaehlt: ${BACKUP_FILE}"
    fi

    if [[ -z "${BACKUP_FILE}" ]]; then
        die "Keine Backup-Datei angegeben. Verwende --latest oder gib einen Pfad an."
    fi

    # Show backup info and verify
    get_backup_info "${BACKUP_FILE}"
    verify_backup "${BACKUP_FILE}"

    if [[ "${DRY_RUN}" == "true" ]]; then
        log "INFO" "Dry-Run Modus: Backup verifiziert, keine Wiederherstellung durchgefuehrt"
        log "INFO" "=========================================="
        exit 0
    fi

    # Safety confirmation
    confirm_restore

    # Perform the restore
    perform_restore "${BACKUP_FILE}"

    log "INFO" "=========================================="
    log "INFO" "Wiederherstellung abgeschlossen"
    log "INFO" "=========================================="

    exit 0
}

main "$@"
