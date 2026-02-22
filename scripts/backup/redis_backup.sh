#!/bin/bash
# =============================================================================
# Redis Backup Script for Ablage-System
# Triggers BGSAVE and copies RDB dump to backup location
# =============================================================================
set -euo pipefail

# -- Configuration (override via environment) ---------------------------------
BACKUP_BASE="${BACKUP_BASE:-/backup}"
BACKUP_DIR="${BACKUP_BASE}/redis"
LOG_DIR="${BACKUP_BASE}/logs"
LOG_FILE="${LOG_DIR}/redis_backup.log"
RETENTION_DAYS="${REDIS_BACKUP_RETENTION_DAYS:-7}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

# Redis connection (defaults match docker-compose.yml)
REDIS_CONTAINER="${REDIS_CONTAINER:-ablage-redis}"
REDIS_PASSWORD="${REDIS_PASSWORD:?REDIS_PASSWORD muss gesetzt sein}"
REDIS_PORT="${REDIS_PORT:-6379}"

# BGSAVE timeout in seconds
BGSAVE_TIMEOUT="${BGSAVE_TIMEOUT:-300}"

# -- Logging ------------------------------------------------------------------
mkdir -p "${LOG_DIR}" "${BACKUP_DIR}"
exec > >(tee -a "${LOG_FILE}") 2>&1

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] FEHLER: $1" >&2
}

# -- Helper: run redis-cli inside container ------------------------------------
redis_cli() {
    docker exec "${REDIS_CONTAINER}" redis-cli -a "${REDIS_PASSWORD}" --no-auth-warning "$@"
}

# -- Pre-flight checks --------------------------------------------------------
log "=== Redis-Backup gestartet ==="
log "Zielverzeichnis: ${BACKUP_DIR}"

# Check container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${REDIS_CONTAINER}$"; then
    log_error "Redis-Container '${REDIS_CONTAINER}' laeuft nicht"
    exit 1
fi

# Check Redis connectivity
if ! redis_cli PING | grep -q "PONG"; then
    log_error "Redis antwortet nicht auf PING"
    exit 1
fi
log "Redis-Verbindung erfolgreich"

# -- Get pre-backup info ------------------------------------------------------
DB_SIZE=$(redis_cli DBSIZE | awk '{print $2}' | tr -d '\r')
MEMORY_USED=$(redis_cli INFO memory | grep "used_memory_human" | cut -d: -f2 | tr -d '\r')
LAST_SAVE_BEFORE=$(redis_cli LASTSAVE | tr -d '\r')
log "Datenbankgroesse: ${DB_SIZE} Keys"
log "Speicherverbrauch: ${MEMORY_USED}"

# -- Trigger BGSAVE -----------------------------------------------------------
log "Starte BGSAVE..."
BGSAVE_RESULT=$(redis_cli BGSAVE 2>&1)

if echo "${BGSAVE_RESULT}" | grep -q "Background saving started\|already in progress"; then
    log "BGSAVE initiiert: ${BGSAVE_RESULT}"
else
    log_error "BGSAVE fehlgeschlagen: ${BGSAVE_RESULT}"
    exit 1
fi

# -- Wait for BGSAVE to complete ----------------------------------------------
log "Warte auf BGSAVE-Abschluss (Timeout: ${BGSAVE_TIMEOUT}s)..."
ELAPSED=0
INTERVAL=2

while [ "${ELAPSED}" -lt "${BGSAVE_TIMEOUT}" ]; do
    LAST_SAVE_AFTER=$(redis_cli LASTSAVE | tr -d '\r')
    BG_STATUS=$(redis_cli INFO persistence | grep "rdb_bgsave_in_progress" | cut -d: -f2 | tr -d '\r')

    if [ "${BG_STATUS}" = "0" ] && [ "${LAST_SAVE_AFTER}" != "${LAST_SAVE_BEFORE}" ]; then
        log "BGSAVE abgeschlossen nach ${ELAPSED}s"
        break
    fi

    sleep "${INTERVAL}"
    ELAPSED=$((ELAPSED + INTERVAL))
done

if [ "${ELAPSED}" -ge "${BGSAVE_TIMEOUT}" ]; then
    log_error "BGSAVE Timeout nach ${BGSAVE_TIMEOUT}s"
    exit 1
fi

# -- Copy RDB dump file -------------------------------------------------------
BACKUP_FILE="${BACKUP_DIR}/redis_dump_${TIMESTAMP}.rdb"
log "Kopiere RDB-Dump nach ${BACKUP_FILE}..."

# Find the dump file inside the container (Redis data dir is /data)
RDB_PATH="/data/dump.rdb"

# Verify RDB file exists in container
if ! docker exec "${REDIS_CONTAINER}" test -f "${RDB_PATH}"; then
    # Try appendonly dir
    RDB_PATH="/data/dump.rdb"
    if ! docker exec "${REDIS_CONTAINER}" test -f "${RDB_PATH}"; then
        log_error "RDB-Datei nicht gefunden im Container"
        exit 1
    fi
fi

# Copy from container to host
docker cp "${REDIS_CONTAINER}:${RDB_PATH}" "${BACKUP_FILE}"

if [ ! -f "${BACKUP_FILE}" ]; then
    log_error "RDB-Kopie fehlgeschlagen"
    exit 1
fi

# Compress the backup
log "Komprimiere Backup..."
gzip "${BACKUP_FILE}"
BACKUP_FILE="${BACKUP_FILE}.gz"

BACKUP_SIZE=$(du -sh "${BACKUP_FILE}" 2>/dev/null | cut -f1)
log "Backup erstellt: ${BACKUP_FILE} (${BACKUP_SIZE})"

# -- Also backup AOF if present -----------------------------------------------
AOF_PATH="/data/appendonly.aof"
if docker exec "${REDIS_CONTAINER}" test -f "${AOF_PATH}" 2>/dev/null; then
    AOF_BACKUP="${BACKUP_DIR}/redis_aof_${TIMESTAMP}.aof"
    log "Sichere AOF-Datei..."
    docker cp "${REDIS_CONTAINER}:${AOF_PATH}" "${AOF_BACKUP}"
    gzip "${AOF_BACKUP}"
    AOF_SIZE=$(du -sh "${AOF_BACKUP}.gz" 2>/dev/null | cut -f1)
    log "AOF-Backup: ${AOF_BACKUP}.gz (${AOF_SIZE})"
fi

# -- Verify backup integrity --------------------------------------------------
log "Verifiziere Backup-Integritaet..."

# Check file is not empty and is valid gzip
if ! gzip -t "${BACKUP_FILE}" 2>/dev/null; then
    log_error "Backup-Datei ist kein gueltiges gzip-Archiv"
    exit 1
fi

COMPRESSED_SIZE=$(stat -c%s "${BACKUP_FILE}" 2>/dev/null || stat -f%z "${BACKUP_FILE}" 2>/dev/null)
if [ "${COMPRESSED_SIZE}" -lt 100 ]; then
    log_error "Backup-Datei ist verdaechtig klein (${COMPRESSED_SIZE} Bytes)"
    exit 1
fi

log "Integritaetspruefung bestanden (${BACKUP_SIZE})"

# -- Retention: keep only N daily backups --------------------------------------
log "Wende Aufbewahrungsrichtlinie an (${RETENTION_DAYS} Tage)..."
DELETED=0

# Count existing RDB backups
BACKUP_COUNT=$(find "${BACKUP_DIR}" -name "redis_dump_*.rdb.gz" -type f 2>/dev/null | wc -l)

if [ "${BACKUP_COUNT}" -gt "${RETENTION_DAYS}" ]; then
    REMOVE_COUNT=$((BACKUP_COUNT - RETENTION_DAYS))
    find "${BACKUP_DIR}" -name "redis_dump_*.rdb.gz" -type f 2>/dev/null | sort | head -n "${REMOVE_COUNT}" | while read -r old_file; do
        log "  Loesche: $(basename "${old_file}")"
        rm -f "${old_file}"
        # Also remove corresponding AOF backup
        AOF_MATCH=$(echo "${old_file}" | sed 's/redis_dump_/redis_aof_/' | sed 's/\.rdb\.gz/.aof.gz/')
        rm -f "${AOF_MATCH}" 2>/dev/null || true
        DELETED=$((DELETED + 1))
    done
    log "  ${REMOVE_COUNT} alte Backups entfernt"
else
    log "  Keine alten Backups zu entfernen (${BACKUP_COUNT}/${RETENTION_DAYS})"
fi

# -- Summary ------------------------------------------------------------------
log "--- Zusammenfassung ---"
log "Backup-Datei: ${BACKUP_FILE}"
log "Groesse: ${BACKUP_SIZE}"
log "Redis Keys: ${DB_SIZE}"
log "Speicher: ${MEMORY_USED}"
log "BGSAVE Dauer: ${ELAPSED}s"
log "=== Redis-Backup erfolgreich abgeschlossen ==="
exit 0
