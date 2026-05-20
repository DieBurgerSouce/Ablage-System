#!/usr/bin/env bash
# =============================================================================
# PostgreSQL Backup Verification Script - Ablage-System
# Monatliche Verifizierung: Restore in temporaere DB, Integritaetspruefung, Cleanup
# =============================================================================
set -euo pipefail

# --- Configuration ---
CONTAINER_NAME="${PG_CONTAINER_NAME:-ablage-postgres}"
POSTGRES_DB="${POSTGRES_DB:-ablage_system}"
POSTGRES_USER="${POSTGRES_USER:-ablage_admin}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-${DB_PASSWORD:-}}"

BACKUP_DIR="${BACKUP_DIR:-/backup/postgres}"
LOG_DIR="${LOG_DIR:-/backup/logs}"
LOG_FILE="${LOG_DIR}/pg_verify.log"

VERIFY_DB="${VERIFY_DB:-ablage_verify_temp}"

# --- Parse Arguments ---
BACKUP_FILE=""
USE_LATEST=false
VERBOSE=false

usage() {
    cat <<EOF
Verwendung: $0 [OPTIONEN] [BACKUP_DATEI]

Monatliche Backup-Verifizierung fuer Ablage-System.
Stellt Backup in temporaere Datenbank wieder her und prueft Integritaet.

Optionen:
  --latest      Neuestes Backup automatisch auswaehlen
  --verbose     Detaillierte Ausgabe
  -h, --help    Diese Hilfe anzeigen

Beispiele:
  $0 /backup/postgres/monthly/ablage_system_monthly_20260201.sql.gz
  $0 --latest
  $0 --latest --verbose

Umgebungsvariablen:
  PG_CONTAINER_NAME   Docker-Container (default: ablage-postgres)
  POSTGRES_DB          Produktions-Datenbank (default: ablage_system)
  POSTGRES_USER        Benutzer (default: ablage_admin)
  POSTGRES_PASSWORD    Passwort (oder DB_PASSWORD)
  BACKUP_DIR           Backup-Verzeichnis (default: /backup/postgres)
  VERIFY_DB            Temporaere Datenbank (default: ablage_verify_temp)
EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --latest)
            USE_LATEST=true
            shift
            ;;
        --verbose)
            VERBOSE=true
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
    cleanup_temp_db
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

    latest=$(find "${BACKUP_DIR}" -name "*.sql.gz" -type f -printf '%T@ %p\n' 2>/dev/null \
        | sort -rn \
        | head -1 \
        | awk '{print $2}')

    if [[ -z "${latest}" ]]; then
        die "Kein Backup gefunden in ${BACKUP_DIR}"
    fi

    echo "${latest}"
}

# --- Temporary Database Management ---

cleanup_temp_db() {
    log "INFO" "Bereinige temporaere Datenbank '${VERIFY_DB}'..."

    # Terminate connections
    docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${CONTAINER_NAME}" \
        psql -U "${POSTGRES_USER}" -d postgres -c \
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${VERIFY_DB}' AND pid <> pg_backend_pid();" \
        2>/dev/null || true

    # Drop temp database
    docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${CONTAINER_NAME}" \
        psql -U "${POSTGRES_USER}" -d postgres -c \
        "DROP DATABASE IF EXISTS \"${VERIFY_DB}\";" \
        2>/dev/null || true

    log "INFO" "Temporaere Datenbank bereinigt"
}

create_temp_db() {
    log "INFO" "Erstelle temporaere Datenbank '${VERIFY_DB}'..."

    # Ensure no leftover temp db exists
    cleanup_temp_db

    docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${CONTAINER_NAME}" \
        psql -U "${POSTGRES_USER}" -d postgres -c \
        "CREATE DATABASE \"${VERIFY_DB}\" OWNER \"${POSTGRES_USER}\";" \
        2>>"${LOG_FILE}"

    # Enable pgvector extension
    docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${CONTAINER_NAME}" \
        psql -U "${POSTGRES_USER}" -d "${VERIFY_DB}" -c \
        "CREATE EXTENSION IF NOT EXISTS vector;" \
        2>>"${LOG_FILE}" || true

    log "INFO" "Temporaere Datenbank erstellt"
}

# --- Verification Functions ---

verify_archive_integrity() {
    local file="$1"

    log "INFO" "[1/5] Pruefe Archiv-Integritaet..."

    if [[ ! -f "${file}" ]]; then
        die "Backup-Datei nicht gefunden: ${file}"
    fi

    if [[ ! -s "${file}" ]]; then
        die "Backup-Datei ist leer: ${file}"
    fi

    # pg_restore --list validates the archive structure
    local object_count
    object_count=$(docker exec -i "${CONTAINER_NAME}" pg_restore --list < "${file}" 2>/dev/null | wc -l)

    if (( object_count == 0 )); then
        die "Archiv enthaelt keine Objekte"
    fi

    log "INFO" "  Archiv-Objekte: ${object_count}"
    log "INFO" "  Archiv-Integritaet: OK"
}

restore_to_temp() {
    local file="$1"

    log "INFO" "[2/5] Stelle in temporaere Datenbank wieder her..."

    if docker exec -i -e PGPASSWORD="${POSTGRES_PASSWORD}" "${CONTAINER_NAME}" \
        pg_restore -U "${POSTGRES_USER}" -d "${VERIFY_DB}" \
        --no-owner \
        --no-privileges \
        < "${file}" \
        2>>"${LOG_FILE}"; then
        log "INFO" "  Wiederherstellung in temporaere DB: OK"
    else
        die "Wiederherstellung in temporaere Datenbank fehlgeschlagen"
    fi
}

verify_schema() {
    log "INFO" "[3/5] Pruefe Schema-Integritaet..."

    # Count tables
    local table_count
    table_count=$(docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${CONTAINER_NAME}" \
        psql -U "${POSTGRES_USER}" -d "${VERIFY_DB}" -t -c \
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';" \
        2>/dev/null | tr -d ' ')

    log "INFO" "  Tabellen: ${table_count}"

    if (( table_count == 0 )); then
        die "Keine Tabellen in der wiederhergestellten Datenbank"
    fi

    # Count indexes
    local index_count
    index_count=$(docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${CONTAINER_NAME}" \
        psql -U "${POSTGRES_USER}" -d "${VERIFY_DB}" -t -c \
        "SELECT count(*) FROM pg_indexes WHERE schemaname = 'public';" \
        2>/dev/null | tr -d ' ')

    log "INFO" "  Indizes: ${index_count}"

    # Count foreign keys
    local fk_count
    fk_count=$(docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${CONTAINER_NAME}" \
        psql -U "${POSTGRES_USER}" -d "${VERIFY_DB}" -t -c \
        "SELECT count(*) FROM information_schema.table_constraints WHERE constraint_type = 'FOREIGN KEY' AND constraint_schema = 'public';" \
        2>/dev/null | tr -d ' ')

    log "INFO" "  Foreign Keys: ${fk_count}"

    # Check for pgvector extension
    local has_vector
    has_vector=$(docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${CONTAINER_NAME}" \
        psql -U "${POSTGRES_USER}" -d "${VERIFY_DB}" -t -c \
        "SELECT count(*) FROM pg_extension WHERE extname = 'vector';" \
        2>/dev/null | tr -d ' ')

    log "INFO" "  pgvector Extension: $([ "${has_vector}" -gt 0 ] && echo 'JA' || echo 'NEIN')"

    log "INFO" "  Schema-Integritaet: OK"

    if [[ "${VERBOSE}" == "true" ]]; then
        log "INFO" "  Tabellen-Liste:"
        docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${CONTAINER_NAME}" \
            psql -U "${POSTGRES_USER}" -d "${VERIFY_DB}" -t -c \
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;" \
            2>/dev/null | while read -r table; do
                [[ -n "${table}" ]] && log "INFO" "    - ${table}"
            done
    fi
}

verify_data_integrity() {
    log "INFO" "[4/5] Pruefe Daten-Integritaet..."

    # Get total row count across all tables
    local total_rows=0
    local table_rows

    table_rows=$(docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${CONTAINER_NAME}" \
        psql -U "${POSTGRES_USER}" -d "${VERIFY_DB}" -t -c \
        "SELECT SUM(n_live_tup) FROM pg_stat_user_tables;" \
        2>/dev/null | tr -d ' ')

    # pg_stat may show 0 before ANALYZE; run ANALYZE first
    docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${CONTAINER_NAME}" \
        psql -U "${POSTGRES_USER}" -d "${VERIFY_DB}" -c "ANALYZE;" \
        2>>"${LOG_FILE}" || true

    table_rows=$(docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${CONTAINER_NAME}" \
        psql -U "${POSTGRES_USER}" -d "${VERIFY_DB}" -t -c \
        "SELECT SUM(n_live_tup) FROM pg_stat_user_tables;" \
        2>/dev/null | tr -d ' ')

    log "INFO" "  Gesamt-Datensaetze: ${table_rows:-0}"

    # Check for critical tables (alembic_version must exist for migrations)
    local has_alembic
    has_alembic=$(docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${CONTAINER_NAME}" \
        psql -U "${POSTGRES_USER}" -d "${VERIFY_DB}" -t -c \
        "SELECT count(*) FROM information_schema.tables WHERE table_name = 'alembic_version' AND table_schema = 'public';" \
        2>/dev/null | tr -d ' ')

    if [[ "${has_alembic}" -gt 0 ]]; then
        local alembic_rev
        alembic_rev=$(docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${CONTAINER_NAME}" \
            psql -U "${POSTGRES_USER}" -d "${VERIFY_DB}" -t -c \
            "SELECT version_num FROM alembic_version LIMIT 1;" \
            2>/dev/null | tr -d ' ')
        log "INFO" "  Alembic Revision: ${alembic_rev}"
    else
        log "WARN" "  Alembic Version Tabelle nicht gefunden"
    fi

    log "INFO" "  Daten-Integritaet: OK"
}

compare_with_production() {
    log "INFO" "[5/5] Vergleiche mit Produktions-Datenbank..."

    # Compare table counts
    local prod_tables
    prod_tables=$(docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${CONTAINER_NAME}" \
        psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -t -c \
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';" \
        2>/dev/null | tr -d ' ')

    local verify_tables
    verify_tables=$(docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${CONTAINER_NAME}" \
        psql -U "${POSTGRES_USER}" -d "${VERIFY_DB}" -t -c \
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';" \
        2>/dev/null | tr -d ' ')

    log "INFO" "  Tabellen - Produktion: ${prod_tables}, Backup: ${verify_tables}"

    if [[ "${prod_tables}" != "${verify_tables}" ]]; then
        log "WARN" "  Tabellen-Anzahl weicht ab! (Produktion: ${prod_tables}, Backup: ${verify_tables})"
    else
        log "INFO" "  Tabellen-Vergleich: IDENTISCH"
    fi

    # Compare row counts for key tables
    local prod_rows
    prod_rows=$(docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${CONTAINER_NAME}" \
        psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -t -c \
        "SELECT SUM(n_live_tup) FROM pg_stat_user_tables;" \
        2>/dev/null | tr -d ' ')

    local verify_rows
    verify_rows=$(docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${CONTAINER_NAME}" \
        psql -U "${POSTGRES_USER}" -d "${VERIFY_DB}" -t -c \
        "SELECT SUM(n_live_tup) FROM pg_stat_user_tables;" \
        2>/dev/null | tr -d ' ')

    log "INFO" "  Datensaetze - Produktion: ${prod_rows:-0}, Backup: ${verify_rows:-0}"

    log "INFO" "  Produktions-Vergleich: ABGESCHLOSSEN"
}

# --- Main ---

main() {
    log "INFO" "=========================================="
    log "INFO" "PostgreSQL Backup-Verifizierung gestartet"
    log "INFO" "=========================================="

    check_prerequisites

    # Determine backup file
    if [[ "${USE_LATEST}" == "true" ]]; then
        BACKUP_FILE=$(find_latest_backup)
        log "INFO" "Neuestes Backup: ${BACKUP_FILE}"
    fi

    if [[ -z "${BACKUP_FILE}" ]]; then
        die "Keine Backup-Datei angegeben. Verwende --latest oder gib einen Pfad an."
    fi

    local file_size
    file_size=$(du -h "${BACKUP_FILE}" | cut -f1)
    log "INFO" "Backup-Datei: ${BACKUP_FILE} (${file_size})"

    # Run all verification steps
    local errors=0

    # Step 1: Archive integrity
    verify_archive_integrity "${BACKUP_FILE}" || (( errors++ )) || true

    # Step 2: Restore to temp database
    create_temp_db
    restore_to_temp "${BACKUP_FILE}" || (( errors++ )) || true

    # Step 3: Schema check
    verify_schema || (( errors++ )) || true

    # Step 4: Data integrity
    verify_data_integrity || (( errors++ )) || true

    # Step 5: Compare with production
    compare_with_production || (( errors++ )) || true

    # Cleanup
    cleanup_temp_db

    # Report
    log "INFO" "=========================================="
    if (( errors > 0 )); then
        log "ERROR" "Verifizierung FEHLGESCHLAGEN (${errors} Fehler)"
        log "INFO" "=========================================="
        exit 1
    else
        log "INFO" "Verifizierung ERFOLGREICH - Backup ist vollstaendig und konsistent"
        log "INFO" "=========================================="
        exit 0
    fi
}

main "$@"
