#!/bin/bash
# =============================================================================
# Backup Restore Verification Script for Ablage-System
# Monthly automated restore test to verify backup integrity
# =============================================================================
set -euo pipefail

# -- Configuration (override via environment) ---------------------------------
BACKUP_BASE="${BACKUP_BASE:-/backup}"
LOG_DIR="${BACKUP_BASE}/logs"
LOG_FILE="${LOG_DIR}/restore_test.log"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

# PostgreSQL connection (for temp DB restore test)
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-ablage-postgres}"
POSTGRES_USER="${POSTGRES_USER:-ablage_admin}"
POSTGRES_DB="${POSTGRES_DB:-ablage_system}"
DB_PASSWORD="${DB_PASSWORD:?DB_PASSWORD muss gesetzt sein}"
TEST_DB="restore_test_${TIMESTAMP}"

# Redis
REDIS_CONTAINER="${REDIS_CONTAINER:-ablage-redis}"
REDIS_PASSWORD="${REDIS_PASSWORD:?REDIS_PASSWORD muss gesetzt sein}"

# Report
REPORT_DIR="${BACKUP_BASE}/logs"
REPORT_FILE="${REPORT_DIR}/restore_test_report_${TIMESTAMP}.txt"

# -- Logging ------------------------------------------------------------------
mkdir -p "${LOG_DIR}"
exec > >(tee -a "${LOG_FILE}") 2>&1

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] FEHLER: $1" >&2
}

# -- Track test results --------------------------------------------------------
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_SKIPPED=0
declare -a TEST_RESULTS=()

record_test() {
    local name="$1"
    local status="$2"
    local detail="${3:-}"

    TEST_RESULTS+=("${status} | ${name} | ${detail}")

    case "${status}" in
        BESTANDEN)
            TESTS_PASSED=$((TESTS_PASSED + 1))
            log "  BESTANDEN: ${name} ${detail}"
            ;;
        FEHLER)
            TESTS_FAILED=$((TESTS_FAILED + 1))
            log_error "  FEHLER: ${name} ${detail}"
            ;;
        UEBERSPRUNGEN)
            TESTS_SKIPPED=$((TESTS_SKIPPED + 1))
            log "  UEBERSPRUNGEN: ${name} ${detail}"
            ;;
    esac
}

# -- Helper: find latest backup file -------------------------------------------
find_latest_backup() {
    local dir="$1"
    local pattern="$2"
    find "${dir}" -name "${pattern}" -type f 2>/dev/null | sort -r | head -1
}

# =============================================================================
# TEST 1: PostgreSQL Restore Verification
# =============================================================================
test_postgres_restore() {
    log ""
    log "=== Test 1: PostgreSQL Restore-Verifizierung ==="

    # Find latest PostgreSQL backup
    local pg_backup
    pg_backup=$(find_latest_backup "${BACKUP_BASE}/postgres" "*.sql.gz")

    if [ -z "${pg_backup}" ]; then
        # Try alternative backup locations
        pg_backup=$(find_latest_backup "${BACKUP_BASE}/postgres" "*.sql")
    fi

    if [ -z "${pg_backup}" ]; then
        record_test "PostgreSQL: Backup-Datei finden" "UEBERSPRUNGEN" "(Kein Backup gefunden)"
        return 0
    fi

    log "Verwende Backup: ${pg_backup}"
    local backup_size
    backup_size=$(du -sh "${pg_backup}" 2>/dev/null | cut -f1)
    record_test "PostgreSQL: Backup-Datei vorhanden" "BESTANDEN" "(${backup_size})"

    # Check container is running
    if ! docker ps --format '{{.Names}}' | grep -q "^${POSTGRES_CONTAINER}$"; then
        record_test "PostgreSQL: Container laeuft" "FEHLER" "(Container nicht gefunden)"
        return 1
    fi
    record_test "PostgreSQL: Container laeuft" "BESTANDEN" ""

    # Create temporary test database
    log "Erstelle temporaere Test-Datenbank: ${TEST_DB}..."
    docker exec "${POSTGRES_CONTAINER}" psql -U "${POSTGRES_USER}" -d postgres \
        -c "CREATE DATABASE ${TEST_DB};" >/dev/null 2>&1

    local restore_exit=0

    # Restore backup to temp database
    log "Stelle Backup in Test-Datenbank wieder her..."
    if [[ "${pg_backup}" == *.gz ]]; then
        # Compressed backup
        if gunzip -c "${pg_backup}" | docker exec -i "${POSTGRES_CONTAINER}" \
            psql -U "${POSTGRES_USER}" -d "${TEST_DB}" >/dev/null 2>&1; then
            record_test "PostgreSQL: Restore in Test-DB" "BESTANDEN" ""
        else
            record_test "PostgreSQL: Restore in Test-DB" "FEHLER" "(psql Fehler)"
            restore_exit=1
        fi
    else
        # Uncompressed backup
        if docker exec -i "${POSTGRES_CONTAINER}" \
            psql -U "${POSTGRES_USER}" -d "${TEST_DB}" < "${pg_backup}" >/dev/null 2>&1; then
            record_test "PostgreSQL: Restore in Test-DB" "BESTANDEN" ""
        else
            record_test "PostgreSQL: Restore in Test-DB" "FEHLER" "(psql Fehler)"
            restore_exit=1
        fi
    fi

    # Verify restored data (if restore succeeded)
    if [ "${restore_exit}" -eq 0 ]; then
        # Count tables
        TABLE_COUNT=$(docker exec "${POSTGRES_CONTAINER}" psql -U "${POSTGRES_USER}" -d "${TEST_DB}" \
            -t -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null | tr -d ' \r\n')

        if [ -n "${TABLE_COUNT}" ] && [ "${TABLE_COUNT}" -gt 0 ]; then
            record_test "PostgreSQL: Tabellen vorhanden" "BESTANDEN" "(${TABLE_COUNT} Tabellen)"
        else
            record_test "PostgreSQL: Tabellen vorhanden" "FEHLER" "(Keine Tabellen gefunden)"
        fi

        # Check critical tables exist
        for table in documents users entities; do
            EXISTS=$(docker exec "${POSTGRES_CONTAINER}" psql -U "${POSTGRES_USER}" -d "${TEST_DB}" \
                -t -c "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = '${table}');" 2>/dev/null | tr -d ' \r\n')
            if [ "${EXISTS}" = "t" ]; then
                ROW_COUNT=$(docker exec "${POSTGRES_CONTAINER}" psql -U "${POSTGRES_USER}" -d "${TEST_DB}" \
                    -t -c "SELECT count(*) FROM ${table};" 2>/dev/null | tr -d ' \r\n')
                record_test "PostgreSQL: Tabelle '${table}'" "BESTANDEN" "(${ROW_COUNT} Zeilen)"
            else
                record_test "PostgreSQL: Tabelle '${table}'" "UEBERSPRUNGEN" "(Tabelle existiert nicht)"
            fi
        done
    fi

    # Cleanup: drop test database
    log "Bereinige Test-Datenbank..."
    docker exec "${POSTGRES_CONTAINER}" psql -U "${POSTGRES_USER}" -d postgres \
        -c "DROP DATABASE IF EXISTS ${TEST_DB};" >/dev/null 2>&1 || true

    record_test "PostgreSQL: Bereinigung" "BESTANDEN" ""
    return "${restore_exit}"
}

# =============================================================================
# TEST 2: MinIO Backup Integrity Verification
# =============================================================================
test_minio_integrity() {
    log ""
    log "=== Test 2: MinIO Backup-Integritaet ==="

    local minio_dir="${BACKUP_BASE}/minio"

    if [ ! -d "${minio_dir}" ]; then
        record_test "MinIO: Backup-Verzeichnis" "UEBERSPRUNGEN" "(Nicht gefunden)"
        return 0
    fi

    # Find latest snapshot directory
    local latest_snapshot
    latest_snapshot=$(find "${minio_dir}" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort -r | head -1)

    if [ -z "${latest_snapshot}" ]; then
        record_test "MinIO: Snapshot vorhanden" "UEBERSPRUNGEN" "(Kein Snapshot gefunden)"
        return 0
    fi

    local snapshot_name
    snapshot_name=$(basename "${latest_snapshot}")
    local snapshot_size
    snapshot_size=$(du -sh "${latest_snapshot}" 2>/dev/null | cut -f1)
    record_test "MinIO: Snapshot vorhanden" "BESTANDEN" "(${snapshot_name}, ${snapshot_size})"

    # Check each bucket directory
    local bucket_count=0
    local total_objects=0

    for bucket_dir in "${latest_snapshot}"/*/; do
        [ -d "${bucket_dir}" ] || continue
        local bucket_name
        bucket_name=$(basename "${bucket_dir}")
        local object_count
        object_count=$(find "${bucket_dir}" -type f 2>/dev/null | wc -l)
        total_objects=$((total_objects + object_count))
        bucket_count=$((bucket_count + 1))
        record_test "MinIO: Bucket '${bucket_name}'" "BESTANDEN" "(${object_count} Objekte)"
    done

    if [ "${bucket_count}" -eq 0 ]; then
        record_test "MinIO: Buckets vorhanden" "UEBERSPRUNGEN" "(Keine Buckets im Backup)"
    else
        record_test "MinIO: Gesamt" "BESTANDEN" "(${bucket_count} Buckets, ${total_objects} Objekte)"
    fi

    # Verify files are readable (spot check)
    local sample_file
    sample_file=$(find "${latest_snapshot}" -type f 2>/dev/null | head -1)
    if [ -n "${sample_file}" ]; then
        if file "${sample_file}" >/dev/null 2>&1; then
            record_test "MinIO: Datei-Lesbarkeit" "BESTANDEN" "(Stichprobe OK)"
        else
            record_test "MinIO: Datei-Lesbarkeit" "FEHLER" "(Datei nicht lesbar)"
            return 1
        fi
    fi

    return 0
}

# =============================================================================
# TEST 3: Redis RDB Verification
# =============================================================================
test_redis_integrity() {
    log ""
    log "=== Test 3: Redis RDB-Verifizierung ==="

    local redis_dir="${BACKUP_BASE}/redis"

    if [ ! -d "${redis_dir}" ]; then
        record_test "Redis: Backup-Verzeichnis" "UEBERSPRUNGEN" "(Nicht gefunden)"
        return 0
    fi

    # Find latest RDB backup
    local rdb_backup
    rdb_backup=$(find_latest_backup "${redis_dir}" "redis_dump_*.rdb.gz")

    if [ -z "${rdb_backup}" ]; then
        record_test "Redis: RDB-Backup" "UEBERSPRUNGEN" "(Kein Backup gefunden)"
        return 0
    fi

    local rdb_size
    rdb_size=$(du -sh "${rdb_backup}" 2>/dev/null | cut -f1)
    record_test "Redis: RDB-Backup vorhanden" "BESTANDEN" "(${rdb_size})"

    # Verify gzip integrity
    if gzip -t "${rdb_backup}" 2>/dev/null; then
        record_test "Redis: gzip-Integritaet" "BESTANDEN" ""
    else
        record_test "Redis: gzip-Integritaet" "FEHLER" "(Korruptes Archiv)"
        return 1
    fi

    # Decompress and verify RDB magic bytes
    local temp_rdb
    temp_rdb=$(mktemp /tmp/redis_test_XXXXXX.rdb)

    gunzip -c "${rdb_backup}" > "${temp_rdb}" 2>/dev/null

    # Check RDB file magic bytes (REDIS)
    local magic
    magic=$(head -c 5 "${temp_rdb}" 2>/dev/null | cat -v)
    if echo "${magic}" | grep -q "REDIS"; then
        record_test "Redis: RDB Magic-Bytes" "BESTANDEN" "(Gueltige RDB-Datei)"
    else
        record_test "Redis: RDB Magic-Bytes" "FEHLER" "(Ungueltiges RDB-Format)"
        rm -f "${temp_rdb}"
        return 1
    fi

    # Check RDB file size is reasonable
    local rdb_bytes
    rdb_bytes=$(stat -c%s "${temp_rdb}" 2>/dev/null || stat -f%z "${temp_rdb}" 2>/dev/null || echo "0")
    if [ "${rdb_bytes}" -gt 100 ]; then
        record_test "Redis: RDB-Dateigroesse" "BESTANDEN" "($(du -sh "${temp_rdb}" | cut -f1))"
    else
        record_test "Redis: RDB-Dateigroesse" "FEHLER" "(Verdaechtig klein: ${rdb_bytes} Bytes)"
        rm -f "${temp_rdb}"
        return 1
    fi

    # Optional: test RDB loadability with redis-check-rdb if available
    if docker exec "${REDIS_CONTAINER}" which redis-check-rdb &>/dev/null 2>&1; then
        # Copy temp RDB into container for verification
        docker cp "${temp_rdb}" "${REDIS_CONTAINER}:/tmp/test_restore.rdb"
        if docker exec "${REDIS_CONTAINER}" redis-check-rdb /tmp/test_restore.rdb >/dev/null 2>&1; then
            record_test "Redis: redis-check-rdb" "BESTANDEN" "(RDB-Datei valide)"
        else
            record_test "Redis: redis-check-rdb" "FEHLER" "(RDB-Validierung fehlgeschlagen)"
        fi
        docker exec "${REDIS_CONTAINER}" rm -f /tmp/test_restore.rdb 2>/dev/null || true
    else
        record_test "Redis: redis-check-rdb" "UEBERSPRUNGEN" "(Tool nicht verfuegbar)"
    fi

    rm -f "${temp_rdb}"
    return 0
}

# =============================================================================
# TEST 4: Docker Volume Backup Verification
# =============================================================================
test_volume_integrity() {
    log ""
    log "=== Test 4: Docker-Volume-Backup-Verifizierung ==="

    local vol_dir="${BACKUP_BASE}/volumes"

    if [ ! -d "${vol_dir}" ]; then
        record_test "Volumes: Backup-Verzeichnis" "UEBERSPRUNGEN" "(Nicht gefunden)"
        return 0
    fi

    local verified=0
    local failed=0

    for vol_subdir in "${vol_dir}"/*/; do
        [ -d "${vol_subdir}" ] || continue
        local vol_name
        vol_name=$(basename "${vol_subdir}")

        # Find latest backup
        local latest_tar
        latest_tar=$(find "${vol_subdir}" -name "*.tar.gz" -type f 2>/dev/null | sort -r | head -1)

        if [ -z "${latest_tar}" ]; then
            record_test "Volume '${vol_name}'" "UEBERSPRUNGEN" "(Kein Backup)"
            continue
        fi

        local tar_size
        tar_size=$(du -sh "${latest_tar}" 2>/dev/null | cut -f1)

        # Verify tar.gz integrity
        if gzip -t "${latest_tar}" 2>/dev/null; then
            # Verify tar listing works
            if tar tzf "${latest_tar}" >/dev/null 2>&1; then
                local file_count
                file_count=$(tar tzf "${latest_tar}" 2>/dev/null | wc -l)
                record_test "Volume '${vol_name}'" "BESTANDEN" "(${tar_size}, ${file_count} Dateien)"
                verified=$((verified + 1))
            else
                record_test "Volume '${vol_name}'" "FEHLER" "(tar-Listing fehlgeschlagen)"
                failed=$((failed + 1))
            fi
        else
            record_test "Volume '${vol_name}'" "FEHLER" "(Korruptes Archiv)"
            failed=$((failed + 1))
        fi
    done

    if [ "${verified}" -eq 0 ] && [ "${failed}" -eq 0 ]; then
        record_test "Volumes: Gesamt" "UEBERSPRUNGEN" "(Keine Volume-Backups)"
    else
        record_test "Volumes: Gesamt" "BESTANDEN" "(${verified} verifiziert, ${failed} fehlerhaft)"
    fi

    return "${failed}"
}

# =============================================================================
# Main Execution
# =============================================================================
log "================================================================"
log "=== Ablage-System Restore-Verifizierung gestartet ==="
log "================================================================"
log "Zeitstempel: ${TIMESTAMP}"
log ""

OVERALL_START=$(date +%s)

# Run all tests (continue even if individual tests fail)
PG_EXIT=0
test_postgres_restore || PG_EXIT=$?

MINIO_EXIT=0
test_minio_integrity || MINIO_EXIT=$?

REDIS_EXIT=0
test_redis_integrity || REDIS_EXIT=$?

VOL_EXIT=0
test_volume_integrity || VOL_EXIT=$?

OVERALL_END=$(date +%s)
OVERALL_DURATION=$((OVERALL_END - OVERALL_START))

# =============================================================================
# Generate Report
# =============================================================================
log ""
log "================================================================"
log "=== RESTORE-TEST BERICHT ==="
log "================================================================"

{
    echo "Ablage-System Restore-Test Bericht"
    echo "==================================="
    echo ""
    echo "Zeitpunkt:  $(date '+%Y-%m-%d %H:%M:%S')"
    echo "Dauer:      ${OVERALL_DURATION}s"
    echo ""
    echo "Ergebnisse:"
    echo "  Bestanden:      ${TESTS_PASSED}"
    echo "  Fehlgeschlagen: ${TESTS_FAILED}"
    echo "  Uebersprungen:  ${TESTS_SKIPPED}"
    echo ""
    echo "Details:"
    echo "--------"
    for result in "${TEST_RESULTS[@]}"; do
        echo "  ${result}"
    done
    echo ""
    if [ "${TESTS_FAILED}" -eq 0 ]; then
        echo "GESAMTERGEBNIS: BESTANDEN"
    else
        echo "GESAMTERGEBNIS: FEHLGESCHLAGEN (${TESTS_FAILED} Fehler)"
    fi
} | tee "${REPORT_FILE}"

log ""
log "Bericht gespeichert: ${REPORT_FILE}"

# -- Summary -------------------------------------------------------------------
if [ "${TESTS_FAILED}" -eq 0 ]; then
    log "=== Restore-Verifizierung BESTANDEN (${TESTS_PASSED} Tests, ${OVERALL_DURATION}s) ==="
    exit 0
else
    log_error "=== Restore-Verifizierung FEHLGESCHLAGEN (${TESTS_FAILED} von $((TESTS_PASSED + TESTS_FAILED + TESTS_SKIPPED)) Tests) ==="
    exit 1
fi
