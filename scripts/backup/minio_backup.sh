#!/bin/bash
# =============================================================================
# MinIO Backup Script for Ablage-System
# Incremental sync of all MinIO buckets using mc (MinIO Client)
# =============================================================================
set -euo pipefail

# -- Configuration (override via environment) ---------------------------------
BACKUP_BASE="${BACKUP_BASE:-/backup}"
BACKUP_DIR="${BACKUP_BASE}/minio"
LOG_DIR="${BACKUP_BASE}/logs"
LOG_FILE="${LOG_DIR}/minio_backup.log"
RETENTION_DAYS="${MINIO_BACKUP_RETENTION_DAYS:-7}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
SNAPSHOT_DIR="${BACKUP_DIR}/${TIMESTAMP}"

# MinIO connection (defaults match docker-compose.yml)
MINIO_ALIAS="${MINIO_ALIAS:-ablage}"
MINIO_ENDPOINT="${MINIO_ENDPOINT:-http://ablage-minio:9000}"
MINIO_ACCESS_KEY="${MINIO_ROOT_USER:?MINIO_ROOT_USER muss gesetzt sein}"
MINIO_SECRET_KEY="${MINIO_ROOT_PASSWORD:?MINIO_ROOT_PASSWORD muss gesetzt sein}"

# Docker container name
MINIO_CONTAINER="${MINIO_CONTAINER:-ablage-minio}"

# -- Logging ------------------------------------------------------------------
mkdir -p "${LOG_DIR}"
exec > >(tee -a "${LOG_FILE}") 2>&1

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] FEHLER: $1" >&2
}

# -- Pre-flight checks --------------------------------------------------------
log "=== MinIO-Backup gestartet ==="
log "Zielverzeichnis: ${SNAPSHOT_DIR}"

# Check if mc is available (try host first, then docker)
USE_DOCKER=false
if command -v mc &>/dev/null; then
    MC_CMD="mc"
    log "MinIO Client (mc) auf Host gefunden"
elif docker exec "${MINIO_CONTAINER}" which mc &>/dev/null 2>&1; then
    USE_DOCKER=true
    MC_CMD="docker exec ${MINIO_CONTAINER} mc"
    log "MinIO Client (mc) im Container gefunden"
else
    # Install mc in a temporary way via docker run
    USE_DOCKER=true
    MC_CMD="docker run --rm --network container:${MINIO_CONTAINER} -v ${BACKUP_DIR}:/backup minio/mc"
    log "Verwende temporaeren MinIO Client Container"
fi

mkdir -p "${SNAPSHOT_DIR}"

# -- Configure mc alias -------------------------------------------------------
log "Konfiguriere MinIO-Alias '${MINIO_ALIAS}'..."

if [ "${USE_DOCKER}" = true ]; then
    docker run --rm \
        --network "$(docker inspect "${MINIO_CONTAINER}" --format '{{range $net, $conf := .NetworkSettings.Networks}}{{$net}}{{end}}' | head -1)" \
        -v "${BACKUP_DIR}:/backup" \
        -e MC_HOST_${MINIO_ALIAS}="${MINIO_ENDPOINT}" \
        minio/mc alias set "${MINIO_ALIAS}" "${MINIO_ENDPOINT}" "${MINIO_ACCESS_KEY}" "${MINIO_SECRET_KEY}" >/dev/null 2>&1 || true

    # Simpler approach: use mc on host with localhost endpoint
    if command -v mc &>/dev/null; then
        USE_DOCKER=false
        MC_CMD="mc"
        MINIO_ENDPOINT="http://127.0.0.1:9000"
    fi
fi

if [ "${USE_DOCKER}" = false ]; then
    ${MC_CMD} alias set "${MINIO_ALIAS}" "${MINIO_ENDPOINT}" "${MINIO_ACCESS_KEY}" "${MINIO_SECRET_KEY}" --api S3v4 >/dev/null 2>&1
fi

# -- Discover and backup buckets ----------------------------------------------
ERRORS=0
TOTAL_OBJECTS=0
TOTAL_SIZE=0

log "Ermittle vorhandene Buckets..."
BUCKETS=$(${MC_CMD} ls "${MINIO_ALIAS}/" 2>/dev/null | awk '{print $NF}' | tr -d '/')

if [ -z "${BUCKETS}" ]; then
    log "Keine Buckets gefunden. Backup wird uebersprungen."
    log "=== MinIO-Backup abgeschlossen (keine Daten) ==="
    exit 0
fi

for bucket in ${BUCKETS}; do
    BUCKET_DIR="${SNAPSHOT_DIR}/${bucket}"
    mkdir -p "${BUCKET_DIR}"
    log "Sichere Bucket: ${bucket} -> ${BUCKET_DIR}"

    # Incremental mirror: only new/changed objects
    if ${MC_CMD} mirror --overwrite --remove=false \
        "${MINIO_ALIAS}/${bucket}" "${BUCKET_DIR}" 2>&1; then
        # Count backed up objects
        OBJECT_COUNT=$(find "${BUCKET_DIR}" -type f 2>/dev/null | wc -l)
        BUCKET_SIZE=$(du -sh "${BUCKET_DIR}" 2>/dev/null | cut -f1)
        TOTAL_OBJECTS=$((TOTAL_OBJECTS + OBJECT_COUNT))
        log "  Bucket '${bucket}': ${OBJECT_COUNT} Objekte, ${BUCKET_SIZE}"
    else
        log_error "Fehler beim Sichern von Bucket '${bucket}'"
        ERRORS=$((ERRORS + 1))
    fi
done

# -- Verify backup integrity --------------------------------------------------
log "Verifiziere Backup-Integritaet..."
VERIFY_ERRORS=0

for bucket in ${BUCKETS}; do
    BUCKET_DIR="${SNAPSHOT_DIR}/${bucket}"

    # Compare object count between source and backup
    SOURCE_COUNT=$(${MC_CMD} ls --recursive "${MINIO_ALIAS}/${bucket}" 2>/dev/null | wc -l || echo "0")
    BACKUP_COUNT=$(find "${BUCKET_DIR}" -type f 2>/dev/null | wc -l)

    if [ "${SOURCE_COUNT}" -ne "${BACKUP_COUNT}" ]; then
        log_error "Integritaetspruefung fehlgeschlagen fuer '${bucket}': Quelle=${SOURCE_COUNT}, Backup=${BACKUP_COUNT}"
        VERIFY_ERRORS=$((VERIFY_ERRORS + 1))
    else
        log "  Bucket '${bucket}': ${SOURCE_COUNT} Objekte verifiziert"
    fi
done

if [ "${VERIFY_ERRORS}" -gt 0 ]; then
    log_error "${VERIFY_ERRORS} Bucket(s) mit Integritaetsfehlern"
    ERRORS=$((ERRORS + VERIFY_ERRORS))
fi

# -- Retention: keep only N daily snapshots ------------------------------------
log "Wende Aufbewahrungsrichtlinie an (${RETENTION_DAYS} Tage)..."
DELETED_COUNT=0

# List snapshot directories sorted by name (date-based), delete oldest
SNAPSHOT_COUNT=$(find "${BACKUP_DIR}" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)
if [ "${SNAPSHOT_COUNT}" -gt "${RETENTION_DAYS}" ]; then
    REMOVE_COUNT=$((SNAPSHOT_COUNT - RETENTION_DAYS))
    find "${BACKUP_DIR}" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort | head -n "${REMOVE_COUNT}" | while read -r old_dir; do
        log "  Loesche alten Snapshot: $(basename "${old_dir}")"
        rm -rf "${old_dir}"
        DELETED_COUNT=$((DELETED_COUNT + 1))
    done
    log "  ${REMOVE_COUNT} alte Snapshots entfernt"
else
    log "  Keine alten Snapshots zu entfernen (${SNAPSHOT_COUNT}/${RETENTION_DAYS})"
fi

# -- Summary ------------------------------------------------------------------
TOTAL_SIZE=$(du -sh "${SNAPSHOT_DIR}" 2>/dev/null | cut -f1)

log "--- Zusammenfassung ---"
log "Snapshot: ${SNAPSHOT_DIR}"
log "Buckets gesichert: $(echo "${BUCKETS}" | wc -w)"
log "Objekte gesamt: ${TOTAL_OBJECTS}"
log "Groesse: ${TOTAL_SIZE}"
log "Fehler: ${ERRORS}"

if [ "${ERRORS}" -gt 0 ]; then
    log_error "MinIO-Backup mit ${ERRORS} Fehler(n) abgeschlossen"
    log "=== MinIO-Backup abgeschlossen (mit Fehlern) ==="
    exit 1
fi

log "=== MinIO-Backup erfolgreich abgeschlossen ==="
exit 0
